from io import StringIO
from unittest.mock import patch
import tracemalloc

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction
from django.http import HttpResponse
from django.test import TestCase, RequestFactory
from django.utils import timezone
from .models import ODT, Revision, EventoRevision
from .facturacion_models import FacturacionContratista, FacturacionODT, PeriodoFacturacion
from .management.commands.diagnosticar_rendimiento_bandeja import medir_peticion, SoloLecturaRequerida


class DiagnosticoRendimientoTests(TestCase):
    def setUp(self):
        self.usuario=User.objects.create_superuser("admin",password="prueba")
        self.odt=ODT.objects.create(numero=1,cuenta_completa="FIR-1",contratista="Prueba",
            servicio="MANTENCION CORRECTIVA CON COBRO",estado_softguard="Finalizado",
            fecha_finalizacion=timezone.now(),valor_pago_tecnico=100,valor_pago_editado=0)

    def ejecutar(self,**opciones):
        argumentos=dict(usuario="admin",fecha_desde="2026-01-01",fecha_hasta="2027-01-01")
        argumentos.update(opciones)
        salida=StringIO()
        with patch("revisiones.vistas.bandeja.coordinadores_para_mostrar",
                   return_value={1:{"nombre":"Responsable","usuario":"jtapia","identificado":True}}):
            call_command("diagnosticar_rendimiento_bandeja",stdout=salida,**argumentos)
        return salida.getvalue()

    def test_mide_render_real_sin_guardar_datos_o_sesion(self):
        modelos=[ODT,Revision,EventoRevision,FacturacionContratista,FacturacionODT,PeriodoFacturacion]
        anteriores=[m.objects.count() for m in modelos]
        from django.contrib.sessions.models import Session
        sesiones=Session.objects.count()
        salida=self.ejecutar()
        self.assertIn("HTTP 200",salida)
        self.assertIn("Consultas Django:",salida)
        self.assertIn("No mide RAM total",salida)
        self.assertNotIn("SELECT",salida)
        self.assertNotIn("FIR-1",salida)
        self.assertEqual(anteriores,[m.objects.count() for m in modelos])
        self.assertEqual(sesiones,Session.objects.count())
        self.odt.refresh_from_db()
        self.assertEqual(self.odt.valor_pago_editado,0)

    def test_repeticiones_acotadas_y_usuario_nuevo_por_peticion(self):
        usuarios=[]
        def vista(request,**opciones):
            usuarios.append(request.user)
            return HttpResponse("ok")
        with patch("revisiones.management.commands.diagnosticar_rendimiento_bandeja.bandeja",
                   side_effect=vista):
            salida=self.ejecutar(repeticiones=2)
        self.assertEqual(salida.count("HTTP 200"),2)
        self.assertIsNot(usuarios[0],usuarios[1])

    def test_parametros_invalidos_no_ejecutan_vista(self):
        for opciones in ({"fecha_desde":"invalida"},{"fecha_hasta":"2025-01-01"},
                         {"repeticiones":0},{"repeticiones":4},{"pagina":0}):
            with self.subTest(opciones=opciones), \
                 patch("revisiones.management.commands.diagnosticar_rendimiento_bandeja.bandeja") as vista:
                with self.assertRaises(CommandError):
                    self.ejecutar(**opciones)
                vista.assert_not_called()

    def test_usuario_ausente_inactivo_o_sin_permiso(self):
        User.objects.create_user("sin_permiso")
        User.objects.create_user("inactivo",is_active=False)
        for usuario in ("ausente","inactivo","sin_permiso"):
            with self.subTest(usuario=usuario), self.assertRaises(CommandError):
                self.ejecutar(usuario=usuario)

    def test_estado_y_servicios_se_transmiten_sin_ampliar_predeterminados(self):
        def vista(request,**opciones):
            self.assertEqual(request.GET.getlist("servicios"),["Servicio A","Servicio B"])
            self.assertEqual(request.GET["estado"],"")
            self.assertEqual(request.GET.getlist("contratista"),["Uno","Dos"])
            self.assertEqual(request.GET["contratistas_filtrados"],"1")
            return HttpResponse("ok")
        with patch("revisiones.management.commands.diagnosticar_rendimiento_bandeja.bandeja",side_effect=vista):
            self.ejecutar(servicio=["Servicio A","Servicio B"],contratista=["Uno","Dos"],estado="")

    def test_creacion_no_impone_los_cuatro_servicios(self):
        def vista(request,**opciones):
            self.assertTrue(opciones["por_creacion"])
            self.assertNotIn("servicios",request.GET)
            return HttpResponse("ok")
        with patch("revisiones.management.commands.diagnosticar_rendimiento_bandeja.bandeja",side_effect=vista):
            self.ejecutar(por_creacion=True)

    def test_intento_de_escritura_se_bloquea(self):
        request=RequestFactory().get("/")
        def escribir(*args,**kwargs):
            ODT.objects.filter(pk=self.odt.pk).update(valor_pago_tecnico=999)
            return HttpResponse("ok")
        with self.assertRaises(SoloLecturaRequerida):
            with transaction.atomic():
                with patch("revisiones.management.commands.diagnosticar_rendimiento_bandeja.bandeja",
                           side_effect=escribir):
                    medir_peticion(request)
        self.odt.refresh_from_db()
        self.assertEqual(self.odt.valor_pago_tecnico,100)

    def test_no_detiene_traza_previa(self):
        propia=not tracemalloc.is_tracing()
        if propia:
            tracemalloc.start()
        try:
            with patch("revisiones.management.commands.diagnosticar_rendimiento_bandeja.bandeja",
                       return_value=HttpResponse("ok")):
                resultado=medir_peticion(RequestFactory().get("/"))
            self.assertIsNone(resultado["pico_python_bytes"])
            self.assertTrue(tracemalloc.is_tracing())
        finally:
            if propia:
                tracemalloc.stop()

    def test_error_no_imprime_informacion_del_driver(self):
        with patch("revisiones.management.commands.diagnosticar_rendimiento_bandeja.bandeja",
                   side_effect=RuntimeError("PASSWORD=privado")):
            with self.assertRaises(CommandError) as error:
                self.ejecutar()
        self.assertNotIn("privado",str(error.exception))
