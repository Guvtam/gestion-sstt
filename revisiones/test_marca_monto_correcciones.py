from decimal import Decimal
from io import StringIO
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.db import transaction
from django.db.models import Sum
from django.test import RequestFactory, TestCase
from django.urls import reverse

from .casos_uso.sincronizacion import ejecutar_sincronizacion
from .consultas.pagos import importe_efectivo
from .consultas.seguimiento_correcciones import consultar_correcciones
from .correcciones import registrar_cambio_manual, verificar_sincronizacion
from .dominio.servicios import SERVICIOS_PRINCIPALES
from .facturacion_models import FacturacionContratista, FacturacionODT, PeriodoFacturacion
from .models import CorreccionODT, EventoCorreccionODT, ODT


class MarcaMontoCorreccionesTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", password="prueba")
        self.temporal = TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.configuracion = self.settings(SSTT_SYNC_LOCK_FILE=self.temporal.name+"/sync.lock")
        self.configuracion.enable()
        self.addCleanup(self.configuracion.disable)

    def crear(self, *, monto=2, servicio=None, original=0):
        odt = ODT.objects.create(numero=100, cuenta_completa="FIR-100", contratista="Proveedor", tecnico="Proveedor",
            servicio=SERVICIOS_PRINCIPALES[1], servicio_editado=servicio, valor_pago_tecnico=original,
            valor_pago_editado=monto, estado_softguard="Finalizado")
        seguimiento = registrar_cambio_manual(odt, self.admin)
        return odt, seguimiento

    def sincronizar(self, monto, servicio=SERVICIOS_PRINCIPALES[1]):
        return ejecutar_sincronizacion(lambda: iter([{"Numero":100,"CuentaCompleta":"FIR-100",
            "Tecnico":"Proveedor", "Servicio":servicio,"ValorPagoTecnico":monto,"Estado":"Finalizado"}]))

    def test_marca_espera_monto_mayor_a_dos_y_luego_usa_monto_real(self):
        odt, seguimiento = self.crear()
        for monto in (0,1,2):
            self.sincronizar(monto)
            seguimiento.refresh_from_db(); odt.refresh_from_db()
            self.assertEqual(seguimiento.estado,"PENDIENTE")
            self.assertEqual(odt.valor_pago_editado,2)
        self.sincronizar(25000)
        seguimiento.refresh_from_db(); odt.refresh_from_db()
        self.assertEqual(seguimiento.estado,"ACTUALIZADA")
        self.assertIsNone(odt.valor_pago_editado)
        self.assertEqual(seguimiento.monto_objetivo,2)
        self.assertTrue(seguimiento.corrige_monto)
        self.assertEqual(ODT.objects.aggregate(monto=Sum(importe_efectivo()))["monto"],25000)
        self.assertEqual(consultar_correcciones().get().monto_objetivo_efectivo,25000)
        self.assertTrue(EventoCorreccionODT.objects.filter(detalle__contains="Marca $2 retirada").exists())
        eventos=EventoCorreccionODT.objects.count()
        self.sincronizar(27000)
        self.assertEqual(EventoCorreccionODT.objects.count(),eventos)
        self.assertEqual(ODT.objects.aggregate(monto=Sum(importe_efectivo()))["monto"],27000)

    def test_cambio_mixto_exige_servicio_y_monto_sin_retirar_marca_antes(self):
        odt, seguimiento=self.crear(servicio=SERVICIOS_PRINCIPALES[0])
        self.sincronizar(25000)
        seguimiento.refresh_from_db(); odt.refresh_from_db()
        self.assertEqual(seguimiento.estado,"PENDIENTE")
        self.assertEqual(odt.valor_pago_editado,2)
        self.sincronizar(2,SERVICIOS_PRINCIPALES[0])
        seguimiento.refresh_from_db()
        self.assertEqual(seguimiento.estado,"PENDIENTE")
        self.sincronizar(25000,SERVICIOS_PRINCIPALES[0])
        seguimiento.refresh_from_db(); odt.refresh_from_db()
        self.assertEqual(seguimiento.estado,"ACTUALIZADA")
        self.assertIsNone(odt.valor_pago_editado)
        self.assertEqual(seguimiento.servicio_objetivo,SERVICIOS_PRINCIPALES[0])

    def test_solo_servicio_no_exige_cambio_monto_y_normaliza_texto(self):
        odt, seguimiento=self.crear(monto=None,servicio=SERVICIOS_PRINCIPALES[0])
        self.sincronizar(0,"  mantencion   correctiva con cobro  ")
        seguimiento.refresh_from_db(); odt.refresh_from_db()
        self.assertEqual(seguimiento.estado,"ACTUALIZADA")
        self.assertEqual(odt.valor_pago_tecnico,0)

    def test_objetivo_concreto_distinto_de_dos_mantiene_coincidencia_exacta(self):
        odt, seguimiento=self.crear(monto=17000)
        self.sincronizar(25000)
        seguimiento.refresh_from_db(); odt.refresh_from_db()
        self.assertEqual(seguimiento.estado,"PENDIENTE")
        self.assertEqual(odt.valor_pago_editado,17000)
        self.sincronizar(17000)
        seguimiento.refresh_from_db()
        self.assertEqual(seguimiento.estado,"ACTUALIZADA")

    def test_marca_ya_resuelta_al_guardar_se_retira_y_queda_registrada(self):
        odt, seguimiento=self.crear(original=25000)
        odt.refresh_from_db()
        self.assertEqual(seguimiento.estado,"ACTUALIZADA")
        self.assertIsNone(odt.valor_pago_editado)
        self.assertEqual(seguimiento.monto_objetivo,2)
        self.assertIn("monto solicitado: $2",EventoCorreccionODT.objects.get().detalle)

    def test_simulacion_no_retira_marca_y_fallo_de_evento_revierte_lote(self):
        odt, seguimiento=self.crear()
        fuente=lambda:iter([{"Numero":100,"Tecnico":"Proveedor","Servicio":SERVICIOS_PRINCIPALES[1],"ValorPagoTecnico":25000}])
        ejecutar_sincronizacion(fuente,simular=True)
        odt.refresh_from_db()
        self.assertEqual(odt.valor_pago_editado,2)
        with patch("revisiones.correcciones.EventoCorreccionODT.objects.create",side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.sincronizar(25000)
        odt.refresh_from_db(); seguimiento.refresh_from_db()
        self.assertEqual(odt.valor_pago_tecnico,0)
        self.assertEqual(odt.valor_pago_editado,2)
        self.assertEqual(seguimiento.estado,"PENDIENTE")

    def test_no_modifica_instantaneas_facturadas_y_estadisticas_usan_monto_real(self):
        from .estadisticas_correcciones import estadisticas_correcciones
        odt, seguimiento=self.crear()
        periodo=PeriodoFacturacion.objects.create(fecha_desde="2026-10-21",fecha_hasta="2026-11-20")
        factura=FacturacionContratista.objects.create(periodo=periodo,contratista="Proveedor")
        item=FacturacionODT.objects.create(facturacion=factura,odt=odt,monto_facturado=700,servicio_facturado="Histórico")
        self.sincronizar(25000)
        item.refresh_from_db()
        self.assertEqual(item.monto_facturado,700)
        request=RequestFactory().get("/"); request.user=self.admin
        with patch("revisiones.estadisticas_correcciones.coordinadores_en_peticion",return_value={100:{"usuario":"rsilva","nombre":"Romina"}}), patch("revisiones.estadisticas_correcciones.render",side_effect=lambda r,t,c:c):
            contexto=estadisticas_correcciones(request)
        self.assertEqual(contexto["total"]["corregido"],25000)
        self.assertEqual(contexto["total"]["diferencia"],0)

    def test_inicializador_usa_regla_marca_y_conserva_solicitud(self):
        ODT.objects.create(numero=100,servicio=SERVICIOS_PRINCIPALES[0],valor_pago_tecnico=25000,valor_pago_editado=2)
        call_command("inicializar_correcciones",stdout=StringIO())
        odt=ODT.objects.get(); seguimiento=CorreccionODT.objects.get()
        self.assertEqual(seguimiento.estado,"ACTUALIZADA")
        self.assertEqual(seguimiento.monto_objetivo,2)
        self.assertIsNone(odt.valor_pago_editado)

    def test_naranjo_por_perfil_no_por_cero_para_coordinador(self):
        import re
        odt, seguimiento=self.crear()
        ODT.objects.create(numero=101,cuenta_completa="FIR-101",contratista="Proveedor",tecnico="Proveedor",
            servicio=SERVICIOS_PRINCIPALES[1],valor_pago_tecnico=0,estado_softguard="Finalizado")
        coordinador=User.objects.create_user("rsilva")
        permiso,_=Permission.objects.get_or_create(content_type=ContentType.objects.get_for_model(ODT),codename="ver_bandeja_sstt")
        coordinador.user_permissions.add(permiso)
        for estado in ("PENDIENTE", "EN_PROCESO", "ACTUALIZADA"):
            seguimiento.estado=estado
            seguimiento.save(update_fields=["estado"])
            for usuario in (self.admin,coordinador):
                self.client.force_login(usuario)
                with patch("revisiones.acceso_coordinadores.identificar_coordinadores_odt",side_effect=lambda numeros:{n:{"usuario":"rsilva","nombre":"Romina","identificado":True} for n in numeros}):
                    respuesta=self.client.get(reverse("bandeja"),{"estado":"","fecha_desde":"","fecha_hasta":""})
                html=respuesta.content.decode()
                filas=dict(re.findall(r'<tr data-numero="(\d+)"[^>]*class="([^"]*)"',html))
                if usuario==coordinador:
                    self.assertNotContains(respuesta,"Monto $0")
                    self.assertNotIn("odt-monto-cero",filas["101"])
                    self.assertEqual("odt-correccion-pendiente" in filas["100"], estado in ("PENDIENTE", "EN_PROCESO"))
                    self.assertNotIn("odt-correccion-pendiente",filas["101"])
                else:
                    self.assertIn("odt-monto-cero",filas["101"])
                    self.assertNotIn("odt-correccion-pendiente",filas["100"])


    def test_historial_muestra_solicitud_dos_y_confirmacion_real(self):
        odt, seguimiento=self.crear()
        self.sincronizar(25000)
        self.client.force_login(self.admin)
        with patch("revisiones.vistas.odt.consultar_historial_odt",return_value=[]):
            respuesta=self.client.get(reverse("historial_odt",args=[100]))
        self.assertEqual(respuesta.status_code,200)
        textos=" ".join(e["observacion"] for e in respuesta.json()["eventos"])
        self.assertIn("monto solicitado: $2",textos)
        self.assertIn("Marca $2 retirada",textos)
        self.assertIn("25000",textos)
