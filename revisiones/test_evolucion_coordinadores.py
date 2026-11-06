from datetime import datetime, timedelta
from io import StringIO
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone
from .models import ODT, ResponsableSoftGuard, ProyeccionCoordinadorODT, AsignacionCoordinadorODT
from .coordinadores_softguard import catalogo_coordinadores, identificar_coordinadores_odt, CoordinadoresNoDisponibles
from .acceso_coordinadores import datos_coordinador, es_coordinador_sstt
from .casos_uso.proyeccion_coordinadores import actualizar_proyeccion
from .admin import VinculoCoordinadorForm, ResponsableSoftGuardForm
from .models import VinculoCoordinador


class EvolucionCoordinadoresTests(TestCase):
    def setUp(self):
        self.fecha = timezone.now()
        self.responsable = ResponsableSoftGuard.objects.create(
            id_softguard=9000, usuario_softguard="nuevo_responsable", nombre="Responsable nuevo")
        self.usuario = User.objects.create_user("nuevo_responsable")
        self.odt = ODT.objects.create(numero=123, cuenta_completa="FIR-100")

    def eventos(self):
        return [{"NumeroODT":123, "IDUsuario":9000, "FechaHora":self.fecha, "Accion":"ALTA"}]

    def proyectar(self):
        with patch("revisiones.servicios_sql.consultar_eventos_coordinadores", return_value=self.eventos()):
            return actualizar_proyeccion()

    def test_nuevo_catalogo_se_utiliza_para_lectura_y_formulario(self):
        self.assertEqual(catalogo_coordinadores()[9000]["nombre"], "Responsable nuevo")
        self.assertEqual(datos_coordinador(self.usuario)["usuario"], "nuevo_responsable")
        self.assertTrue(es_coordinador_sstt(self.usuario))
        otro = User.objects.create_user("login_alternativo")
        form = VinculoCoordinadorForm(data={"usuario":otro.pk, "usuario_softguard":"nuevo_responsable", "activo":False})
        self.assertTrue(form.is_valid(), form.errors)

    def test_nuevo_id_infiere_responsable_desde_eventos(self):
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores", return_value=self.eventos()):
            self.assertEqual(identificar_coordinadores_odt([123])[123]["usuario"], "nuevo_responsable")

    def test_desactivar_identidad_no_convierte_en_usuario_sin_restriccion(self):
        self.responsable.activo = False
        self.responsable.save()
        self.assertIsNone(datos_coordinador(self.usuario))
        self.assertTrue(es_coordinador_sstt(self.usuario))

    def test_desactivar_identidad_historica_conserva_restriccion(self):
        from .coordinadores_softguard import COORDINADORES_SOFTGUARD
        ident, datos = next(iter(COORDINADORES_SOFTGUARD.items()))
        ResponsableSoftGuard.objects.update_or_create(id_softguard=ident, defaults={
            "usuario_softguard":datos["usuario"], "nombre":"Suspendido", "activo":False})
        usuario = User.objects.create_user(datos["usuario"])
        self.assertIsNone(datos_coordinador(usuario))
        self.assertTrue(es_coordinador_sstt(usuario))

    def test_formulario_normaliza_login_y_rechaza_id_cero(self):
        form = ResponsableSoftGuardForm(data={"id_softguard":9001,"nombre":"Otra", "usuario_softguard":"OTRA", "activo":True})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["usuario_softguard"], "otra")
        form = ResponsableSoftGuardForm(data={"id_softguard":0,"nombre":"Otra","usuario_softguard":"otra"})
        self.assertFalse(form.is_valid())

    def test_proyeccion_vigente_no_consulta_origen(self):
        self.assertEqual(self.proyectar(), 1)
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores", side_effect=RuntimeError) as origen:
            dato = identificar_coordinadores_odt([123])[123]
        origen.assert_not_called()
        self.assertEqual(dato["usuario"], "nuevo_responsable")
        self.assertIsInstance(dato["fecha_ultima_accion"], datetime)

    def test_asignacion_manual_prevalece_sobre_proyeccion(self):
        self.proyectar()
        AsignacionCoordinadorODT.objects.create(odt=self.odt, usuario_coordinador="jtapia")
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores") as origen:
            dato = identificar_coordinadores_odt([123])[123]
        origen.assert_not_called()
        self.assertEqual(dato["usuario"], "jtapia")
        self.assertTrue(dato["asignacion_manual"])

    def test_caducidad_no_autoriza_con_datos_antiguos_si_origen_falla(self):
        self.proyectar()
        ProyeccionCoordinadorODT.objects.update(verificado_en=self.fecha-timedelta(hours=7))
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores", side_effect=RuntimeError):
            with self.assertRaises(CoordinadoresNoDisponibles):
                identificar_coordinadores_odt([123])

    def test_cambio_catalogo_invalida_proyeccion(self):
        self.proyectar()
        self.responsable.activo=False
        self.responsable.save()
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores", return_value=[]) as origen:
            dato=identificar_coordinadores_odt([123])[123]
        origen.assert_called_once()
        self.assertFalse(dato["identificado"])

    def test_sin_responsable_tambien_se_proyecta_sin_inventar_identidad(self):
        with patch("revisiones.servicios_sql.consultar_eventos_coordinadores", return_value=[]):
            actualizar_proyeccion()
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores") as origen:
            self.assertFalse(identificar_coordinadores_odt([123])[123]["identificado"])
        origen.assert_not_called()

    def test_simular_no_escribe_y_repetir_no_duplica(self):
        with patch("revisiones.servicios_sql.consultar_eventos_coordinadores", return_value=self.eventos()):
            actualizar_proyeccion(simular=True)
        self.assertFalse(ProyeccionCoordinadorODT.objects.exists())
        self.proyectar()
        self.proyectar()
        self.assertEqual(ProyeccionCoordinadorODT.objects.count(), 1)

    def test_fallo_origen_no_sustituye_proyeccion(self):
        self.proyectar()
        anterior = ProyeccionCoordinadorODT.objects.get().resultado
        with patch("revisiones.servicios_sql.consultar_eventos_coordinadores", side_effect=RuntimeError("privado")):
            with self.assertRaises(CommandError) as exc:
                call_command("sincronizar_coordinadores", stdout=StringIO())
        self.assertNotIn("privado", str(exc.exception))
        self.assertEqual(ProyeccionCoordinadorODT.objects.get().resultado, anterior)

    def test_lotes_acotados_y_presupuesto_local_constante(self):
        ODT.objects.bulk_create([ODT(numero=n) for n in range(124, 375)])
        with patch("revisiones.servicios_sql.consultar_eventos_coordinadores", return_value=[]) as origen:
            actualizar_proyeccion()
        self.assertEqual(origen.call_count, 2)
        self.assertTrue(all(len(llamada.args[0]) <= 250 for llamada in origen.call_args_list))
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores") as origen:
            with self.assertNumQueries(2):
                self.assertEqual(len(identificar_coordinadores_odt(range(123, 373))), 250)
        origen.assert_not_called()

    def test_opcion_desactivar_proyeccion_consulta_origen(self):
        self.proyectar()
        with self.settings(SSTT_COORDINADORES_VIGENCIA_HORAS=0):
            with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores", return_value=[]) as origen:
                identificar_coordinadores_odt([123])
        origen.assert_called_once()

    def test_sync_odt_opcional_renueva_responsables(self):
        from .casos_uso.sincronizacion import Resultado
        with patch("revisiones.management.commands.sincronizar_odts.ejecutar_sincronizacion", return_value=Resultado()):
            with patch("revisiones.management.commands.sincronizar_odts.call_command") as comando:
                call_command("sincronizar_odts", con_coordinadores=True, stdout=StringIO())
        self.assertEqual(comando.call_args.args, ("sincronizar_coordinadores",))

    def test_simular_no_renueva_responsables(self):
        from .casos_uso.sincronizacion import Resultado
        with patch("revisiones.management.commands.sincronizar_odts.ejecutar_sincronizacion", return_value=Resultado()):
            with patch("revisiones.management.commands.sincronizar_odts.call_command") as comando:
                call_command("sincronizar_odts", con_coordinadores=True, simular=True, stdout=StringIO())
        comando.assert_not_called()
