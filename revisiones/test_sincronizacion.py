from datetime import datetime, timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from django.contrib import admin
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from .casos_uso.sincronizacion import ejecutar_sincronizacion
from .integraciones.bloqueo_sync import bloquear_sincronizacion, SincronizacionEnCurso
from .integraciones.transformacion_odt import transformar_registro, RegistroOrigenInvalido
from .models import (
    AsignacionCoordinadorODT, CatalogoCuenta, CorreccionODT, EjecucionSincronizacion,
    EventoCorreccionODT, ODT, Revision,
)
from .facturacion_models import FacturacionODT, FacturacionContratista, PeriodoFacturacion
from .servicios_sql import iterar_odts_completas, consultar_odts_completas


def registro(numero, **extra):
    return {
        "Numero": numero, "CuentaCompleta": f"FIR-{numero} - Cliente",
        "Tecnico": "Técnico", "Estado": "Finalizado",
        "Servicio": "MANTENIMIENTO PREVENTIVO", "ValorPagoTecnico": Decimal("100"),
        **extra,
    }


class SincronizacionTests(TestCase):
    def setUp(self):
        self.directorio = TemporaryDirectory()
        self.addCleanup(self.directorio.cleanup)
        self.ruta = str(Path(self.directorio.name) / "sincronizacion.lock")
        self.configuracion = self.settings(SSTT_SYNC_LOCK_FILE=self.ruta)
        self.configuracion.enable()
        self.addCleanup(self.configuracion.disable)
        self.origen = timezone.make_aware(datetime(2026, 11, 6, 5))

    def ejecutar(self, registros, **opciones):
        return ejecutar_sincronizacion(lambda: iter(registros), **opciones)

    def test_completa_registra_duracion_contadores_y_fecha_origen(self):
        resultado = self.ejecutar([registro(1, FechaCarga=self.origen), registro(2)], tamano_lote=1)
        historial = EjecucionSincronizacion.objects.get()
        self.assertEqual(historial.estado, "COMPLETADA")
        self.assertEqual((historial.consultadas, historial.creadas, historial.cuentas_incorporadas), (2, 2, 2))
        self.assertEqual(historial.fecha_carga_origen, self.origen)
        self.assertGreaterEqual(historial.duracion, timedelta(0))
        self.assertIsNotNone(historial.finalizada_en)
        self.assertEqual(resultado.ejecucion_id, historial.pk)

    def test_idempotencia_no_reescribe_odt_ni_duplica_eventos(self):
        datos = registro(1)
        self.ejecutar([datos])
        with CaptureQueriesContext(connection) as capturadas:
            segunda = self.ejecutar([datos])
        self.assertEqual((segunda.creadas, segunda.actualizadas, segunda.sin_cambios), (0, 0, 1))
        self.assertEqual(ODT.objects.count(), 1)
        self.assertEqual(EventoCorreccionODT.objects.count(), 0)
        self.assertFalse(any(q["sql"].startswith('UPDATE "revisiones_odt"') for q in capturadas))

    def test_completa_contratista_aunque_origen_no_cambie_y_es_idempotente(self):
        datos = registro(78781, Tecnico="T. EXTERNO - Técnico")
        self.ejecutar([datos])
        ODT.objects.filter(numero=78781).update(contratista="")
        resultado = self.ejecutar([datos])
        self.assertEqual(resultado.actualizadas, 1)
        self.assertEqual(ODT.objects.get(numero=78781).contratista, datos["Tecnico"])
        self.assertEqual(self.ejecutar([datos]).sin_cambios, 1)

    def test_completa_contratista_cuando_se_asigna_tecnico_despues(self):
        self.ejecutar([registro(1, Tecnico=None)])
        resultado = self.ejecutar([registro(1, Tecnico="Técnico nuevo")])
        self.assertEqual(resultado.actualizadas, 1)
        odt = ODT.objects.get(numero=1)
        self.assertEqual((odt.tecnico, odt.contratista), ("Técnico nuevo", "Técnico nuevo"))

    def test_sin_tecnico_no_inventa_contratista_y_conserva_asignacion(self):
        self.ejecutar([registro(1, Tecnico=None), registro(2)])
        ODT.objects.filter(numero=2).update(contratista="Asignación local")
        self.ejecutar([registro(1, Tecnico=None), registro(2, Tecnico=None)])
        self.assertEqual(ODT.objects.get(numero=1).contratista, "")
        self.assertEqual(ODT.objects.get(numero=2).contratista, "Asignación local")

    def test_simular_informa_reparacion_sin_escribir(self):
        datos = registro(1)
        self.ejecutar([datos])
        ODT.objects.filter(numero=1).update(contratista="")
        with CaptureQueriesContext(connection) as consultas:
            resultado = self.ejecutar([datos], simular=True)
        self.assertEqual(resultado.actualizadas, 1)
        self.assertEqual(ODT.objects.get(numero=1).contratista, "")
        self.assertFalse(any(q["sql"].split()[0] in {"INSERT", "UPDATE", "DELETE"} for q in consultas))

    def test_lote_grande_respeta_limites_sqlite_y_actualiza_ambos_extremos(self):
        self.ejecutar((registro(n) for n in range(1, 1001)), tamano_lote=1000)
        segunda = self.ejecutar((registro(n, ValorPagoTecnico=250) for n in range(1, 1001)), tamano_lote=1000)
        self.assertEqual((segunda.consultadas, segunda.actualizadas), (1000, 1000))
        self.assertEqual(ODT.objects.get(numero=1).valor_pago_tecnico, 250)
        self.assertEqual(ODT.objects.get(numero=1000).valor_pago_tecnico, 250)

    def test_preserva_decisiones_locales_e_instantanea_facturada(self):
        odt = ODT.objects.create(numero=1, contratista="Asignación local", servicio="Original",
            servicio_editado="Servicio manual", valor_pago_tecnico=50, valor_pago_editado=0,
            modificado_manualmente=True, estado_informe="ENVIADO")
        revision = Revision.objects.create(odt=odt, estado="RECHAZADA", observacion="Decisión local")
        AsignacionCoordinadorODT.objects.create(odt=odt, usuario_coordinador="rsilva")
        periodo = PeriodoFacturacion.objects.create(fecha_desde="2026-10-21", fecha_hasta="2026-11-20")
        factura = FacturacionContratista.objects.create(periodo=periodo, contratista="Local")
        item = FacturacionODT.objects.create(odt=odt, facturacion=factura,
            servicio_facturado="Instantánea", monto_facturado=80)
        self.ejecutar([registro(1, Tecnico="Otro", Servicio="Nuevo original", ValorPagoTecnico=200)])
        odt.refresh_from_db()
        revision.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual((odt.servicio, odt.valor_pago_tecnico), ("Nuevo original", Decimal("200")))
        self.assertEqual((odt.servicio_editado, odt.valor_pago_editado), ("Servicio manual", Decimal("0")))
        self.assertEqual((odt.contratista, odt.estado_informe), ("Asignación local", "ENVIADO"))
        self.assertTrue(odt.modificado_manualmente)
        self.assertEqual(revision.estado, "RECHAZADA")
        self.assertEqual(odt.asignacion_coordinador.usuario_coordinador, "rsilva")
        self.assertEqual((item.servicio_facturado, item.monto_facturado), ("Instantánea", Decimal("80")))

    def test_actualiza_correccion_por_coincidencia_sin_borrar_objetivo(self):
        odt = ODT.objects.create(numero=1, valor_pago_tecnico=50, valor_pago_editado=100)
        seguimiento = CorreccionODT.objects.create(odt=odt, estado="EN_PROCESO",
            corrige_monto=True, monto_objetivo=100)
        self.ejecutar([registro(1)])
        seguimiento.refresh_from_db()
        odt.refresh_from_db()
        self.assertEqual(seguimiento.estado, "ACTUALIZADA")
        self.assertEqual(odt.valor_pago_editado, 100)
        self.ejecutar([registro(1)])
        self.assertEqual(EventoCorreccionODT.objects.count(), 1)

    def test_catalogo_existente_no_se_sobrescribe(self):
        CatalogoCuenta.objects.create(codigo_cuenta="FIR-1", tipo_cliente="B2B", ceco="CECO-PRUEBA")
        self.ejecutar([registro(1), registro(2)])
        self.assertEqual(ODT.objects.get(numero=1).tipo_cliente, "B2B")
        self.assertEqual(ODT.objects.get(numero=2).tipo_cliente, "B2C")
        self.assertEqual(CatalogoCuenta.objects.get(codigo_cuenta="FIR-1").ceco, "CECO-PRUEBA")

    def test_omisiones_no_se_presentan_como_completa(self):
        self.ejecutar([registro(9)])
        self.ejecutar([registro(None), registro(0), registro(-1), registro("1.5"), registro(1), registro(1)])
        ultima = EjecucionSincronizacion.objects.first()
        self.assertEqual((ultima.estado, ultima.consultadas, ultima.omitidas), ("CON_OMISIONES", 6, 5))
        self.assertEqual(EjecucionSincronizacion.objects.filter(estado="COMPLETADA").count(), 1)
        self.assertEqual(set(ODT.objects.values_list("numero", flat=True)), {1, 9})

    def test_fallo_en_lote_revierte_lote_y_contadores(self):
        with patch("revisiones.casos_uso.sincronizacion.verificar_sincronizacion", side_effect=RuntimeError):
            ODT.objects.create(numero=1, servicio="Anterior")
            with self.assertRaises(RuntimeError):
                self.ejecutar([registro(1), registro(2)], tamano_lote=2)
        self.assertEqual(ODT.objects.get(numero=1).servicio, "Anterior")
        self.assertFalse(ODT.objects.filter(numero=2).exists())
        ultima = EjecucionSincronizacion.objects.get()
        self.assertEqual((ultima.estado, ultima.creadas, ultima.actualizadas, ultima.consultadas), ("FALLIDA", 0, 0, 2))
        self.assertEqual(CatalogoCuenta.objects.count(), 0)

    def test_fallo_origen_preserva_lotes_confirmados_y_cierra_generador(self):
        cerrado = []
        def fuente():
            try:
                yield registro(1)
                yield registro(2)
                yield registro(3)
                raise RuntimeError("No exponer detalles de conexión")
            finally:
                cerrado.append(True)
        with self.assertRaises(RuntimeError):
            ejecutar_sincronizacion(fuente, tamano_lote=2)
        self.assertEqual(set(ODT.objects.values_list("numero", flat=True)), {1, 2})
        ultima = EjecucionSincronizacion.objects.get()
        self.assertEqual((ultima.estado, ultima.consultadas, ultima.creadas), ("FALLIDA", 3, 2))
        self.assertEqual(ultima.codigo_error, "RuntimeError")
        self.assertEqual(cerrado, [True])
        self.ejecutar([registro(3)])  # El fallo libera el bloqueo.
        self.assertTrue(ODT.objects.filter(numero=3).exists())

    def test_simular_no_escribe_ni_recupera_historial_ni_vincula(self):
        anterior = EjecucionSincronizacion.objects.create()
        with patch("contratistas.vinculacion.aplicar_exactas") as vincular, CaptureQueriesContext(connection) as consultas:
            resultado = self.ejecutar([registro(1)], simular=True)
        self.assertEqual(resultado.creadas, 1)
        self.assertEqual(ODT.objects.count(), 0)
        self.assertEqual(CatalogoCuenta.objects.count(), 0)
        self.assertEqual(EjecucionSincronizacion.objects.count(), 1)
        anterior.refresh_from_db()
        self.assertEqual(anterior.estado, "EN_CURSO")
        vincular.assert_not_called()
        self.assertFalse(any(q["sql"].split()[0] in {"INSERT", "UPDATE", "DELETE"} for q in consultas))

    def test_bloqueo_rechaza_segundo_sync_antes_de_leer_origen(self):
        fuente = MagicMock()
        with bloquear_sincronizacion():
            with self.assertRaises(SincronizacionEnCurso):
                ejecutar_sincronizacion(fuente)
        fuente.assert_not_called()
        self.assertFalse(EjecucionSincronizacion.objects.exists())

    def test_bloqueo_entre_procesos_del_mismo_host(self):
        codigo = '''
import os
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings_test"
import django
django.setup()
from django.conf import settings
settings.SSTT_SYNC_LOCK_FILE = RUTA
from revisiones.integraciones.bloqueo_sync import bloquear_sincronizacion, SincronizacionEnCurso
try:
    with bloquear_sincronizacion():
        raise SystemExit(3)
except SincronizacionEnCurso:
    print("Bloqueado")
'''.replace("RUTA", repr(self.ruta))
        with bloquear_sincronizacion():
            hijo = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, timeout=15)
        self.assertEqual(hijo.returncode, 0, hijo.stderr)
        self.assertIn("Bloqueado", hijo.stdout)

    def test_recupera_historial_huerfano_al_siguiente_intento(self):
        anterior = EjecucionSincronizacion.objects.create(creadas=4)
        self.ejecutar([])
        anterior.refresh_from_db()
        self.assertEqual(anterior.estado, "INTERRUMPIDA")
        self.assertEqual(anterior.creadas, 4)
        self.assertIsNotNone(anterior.finalizada_en)
        self.assertEqual(EjecucionSincronizacion.objects.first().estado, "COMPLETADA")

    def test_ctrl_c_registra_interrupcion(self):
        def fuente():
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            ejecutar_sincronizacion(fuente)
        self.assertEqual(EjecucionSincronizacion.objects.get().estado, "INTERRUMPIDA")

    def test_fallo_vinculacion_no_deshace_odt_y_registra_fallo(self):
        with patch("contratistas.vinculacion.aplicar_exactas", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.ejecutar([registro(1)])
        self.assertTrue(ODT.objects.filter(numero=1).exists())
        ultima = EjecucionSincronizacion.objects.get()
        self.assertEqual((ultima.estado, ultima.creadas, ultima.equivalencias_creadas), ("FALLIDA", 1, 0))

    def test_comando_oculta_mensaje_driver_y_estado_no_lee_sql(self):
        salida = StringIO()
        with patch("revisiones.management.commands.sincronizar_odts.iterar_odts_completas",
                   side_effect=RuntimeError("PWD=secreto-inventado")):
            with self.assertRaises(CommandError) as error:
                call_command("sincronizar_odts", stdout=salida)
        self.assertNotIn("secreto-inventado", str(error.exception))
        with patch("revisiones.servicios_sql.obtener_conexion_sql") as conexion:
            call_command("estado_sincronizacion", stdout=salida)
        conexion.assert_not_called()
        self.assertIn("Fallida", salida.getvalue())
        self.assertNotIn("secreto-inventado", salida.getvalue())

    def test_origen_vacio_no_borra_datos_previos(self):
        ODT.objects.create(numero=1)
        self.ejecutar([])
        self.assertEqual(ODT.objects.count(), 1)
        self.assertEqual(EjecucionSincronizacion.objects.get().consultadas, 0)

    def test_tamano_invalido_no_lee_origen_ni_crea_historial(self):
        fuente = MagicMock()
        for tamano in (0, -1, 1001):
            with self.assertRaises(ValueError):
                ejecutar_sincronizacion(fuente, tamano_lote=tamano)
        fuente.assert_not_called()
        self.assertFalse(EjecucionSincronizacion.objects.exists())

    def test_admin_historial_solo_lectura(self):
        request = RequestFactory().get("/")
        request.user = User.objects.create_superuser("admin", password="prueba")
        vista = admin.site._registry[EjecucionSincronizacion]
        self.assertTrue(vista.has_view_permission(request))
        self.assertFalse(vista.has_add_permission(request))
        self.assertFalse(vista.has_change_permission(request))
        self.assertFalse(vista.has_delete_permission(request))


class LecturaOrigenTests(SimpleTestCase):
    def conexion(self):
        conexion = MagicMock()
        cursor = conexion.cursor.return_value
        cursor.description = [("Numero",), ("CuentaCompleta",)]
        cursor.fetchmany.side_effect = [[(1, "FIR-1"), (2, "FIR-2")], [(3, "FIR-3")], []]
        return conexion, cursor

    def test_stream_fetchmany_sin_fetchall_y_cierre_normal(self):
        conexion, cursor = self.conexion()
        with patch("revisiones.servicios_sql.obtener_conexion_sql", return_value=conexion):
            filas = list(iterar_odts_completas(tamano_lote=2))
        self.assertEqual([r["Numero"] for r in filas], [1, 2, 3])
        cursor.fetchall.assert_not_called()
        cursor.close.assert_called_once()
        conexion.close.assert_called_once()

    def test_stream_cierre_anticipado(self):
        conexion, cursor = self.conexion()
        with patch("revisiones.servicios_sql.obtener_conexion_sql", return_value=conexion):
            filas = iterar_odts_completas()
            self.assertEqual(next(filas)["Numero"], 1)
            filas.close()
        cursor.close.assert_called_once()
        conexion.close.assert_called_once()

    def test_stream_error_de_consulta_tambien_cierra(self):
        conexion, cursor = self.conexion()
        cursor.execute.side_effect = RuntimeError("Fallo simulado")
        with patch("revisiones.servicios_sql.obtener_conexion_sql", return_value=conexion):
            with self.assertRaises(RuntimeError):
                list(iterar_odts_completas())
        cursor.close.assert_called_once()
        conexion.close.assert_called_once()

    def test_compatibilidad_consulta_completa_sigue_devolviendo_lista(self):
        conexion, cursor = self.conexion()
        with patch("revisiones.servicios_sql.obtener_conexion_sql", return_value=conexion):
            filas = consultar_odts_completas(limite=3)
        self.assertIsInstance(filas, list)
        self.assertEqual(len(filas), 3)
        self.assertIn("TOP (3)", cursor.execute.call_args.args[0])

    def test_fecha_invalida_omite_registro_y_fecha_1900_se_limpia(self):
        with self.assertRaises(RegistroOrigenInvalido):
            transformar_registro(registro(1, FechaCreacion="fecha-malformada"))
        _, datos = transformar_registro(registro(1, FechaCreacion=datetime(1900, 1, 1)))
        self.assertIsNone(datos["fecha_creacion"])

    def test_transformacion_no_acepta_campos_manuales_del_origen(self):
        _, datos = transformar_registro(registro(1, servicio_editado="No importar",
            valor_pago_editado=5, contratista="No importar", estado_informe="ENVIADO"))
        self.assertFalse({"servicio_editado", "valor_pago_editado", "contratista", "estado_informe"} & datos.keys())
