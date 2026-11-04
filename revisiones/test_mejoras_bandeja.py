from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch
from django.contrib.auth.models import User
from django.http import QueryDict
from django.template import engines
from django.test import RequestFactory, TestCase
from django.utils import timezone
from .models import ODT
from . import views
from .facturacion import _odts
from .exportar_pdf import generar_pdf_contratista


class MejorasBandejaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("admin", password="test")
        self.factory = RequestFactory()
        for numero, contratista in ((1, "Contratista A"), (2, "Contratista B")):
            ODT.objects.create(numero=numero, contratista=contratista, servicio=views.SERVICIOS_PRINCIPALES[0],
                               valor_pago_tecnico=100, estado_softguard="Finalizado",
                               fecha_finalizacion=timezone.make_aware(datetime(2026, 10, 25)))

    def bandeja(self, **datos):
        request = self.factory.get("/", {"estado": "Finalizado", "fecha_desde": "2026-10-21",
                                        "fecha_hasta": "2026-11-20", **datos})
        request.user = self.user
        with patch("revisiones.views.identificar_coordinador_odt", return_value={"identificado": False}), \
             patch("revisiones.views.render", side_effect=lambda r, t, c: c):
            return views.bandeja(request)

    def test_todos_los_contratistas_marcados_por_defecto(self):
        context = self.bandeja()
        self.assertEqual(context["contratistas_seleccionados"], ["Contratista A", "Contratista B"])
        self.assertEqual(len(context["registros"]), 2)

    def test_deseleccionar_uno_o_todos_se_conserva(self):
        context = self.bandeja(contratistas_filtrados="1", contratista=["Contratista A"])
        self.assertEqual({o.numero for o in context["registros"]}, {1})
        context = self.bandeja(contratistas_filtrados="1")
        self.assertEqual(list(context["registros"]), [])
        self.assertIn("contratistas_filtrados=1", context["querystring"])

    def test_ninguno_marcado_no_factura_a_todos(self):
        datos = QueryDict("contratistas_filtrados=1")
        self.assertFalse(_odts(date(2026, 10, 21), date(2026, 11, 20), [], [], datos).exists())

    def test_servicio_fuera_catalogo_rechazado(self):
        request = self.factory.post("/", {"numero": "1", "servicio": "Inventado",
                                         "monto": "100", "estado": "APROBADA"})
        request.user = self.user
        self.assertEqual(views.guardar_fila(request).status_code, 400)

    def test_servicio_permitido_se_guarda(self):
        request = self.factory.post("/", {"numero": "1", "servicio": views.SERVICIOS_PRINCIPALES[1],
                                         "monto": "100", "estado": "APROBADA"})
        request.user = self.user
        self.assertEqual(views.guardar_fila(request).status_code, 200)
        self.assertEqual(ODT.objects.get(numero=1).servicio_editado, views.SERVICIOS_PRINCIPALES[1])

    def test_plantilla_selector_y_estado_pago(self):
        context = self.bandeja()
        from types import SimpleNamespace
        context["request"] = SimpleNamespace(user=self.user)
        template = engines["django"].get_template("revisiones/bandeja.html")
        with patch("django.urls.reverse", return_value="/test/"):
            html = template.render(context)
        self.assertIn("Estado pago</th>", html)
        self.assertIn("<select", html)
        self.assertNotIn('type="text"\n                    class="row-input service-input', html)
        for servicio in views.SERVICIOS_PRINCIPALES:
            self.assertIn('value="' + servicio + '"', html)

    def test_pdf_resumen_primera_pagina_historial_segunda(self):
        from pypdf import PdfReader
        registros = [(o, o.servicio, o.valor_pago_tecnico, o.contratista) for o in ODT.objects.all()]
        with patch("revisiones.exportar_pdf.consultar_historial_odt", return_value=[
            {"FechaHora": datetime(2026, 10, 25, 10), "Accion": "FINALIZADO",
             "NombreUsuario": "Usuario de prueba", "Observacion": "Trabajo terminado y verificado."}]):
            pdf = generar_pdf_contratista("Contratista de prueba", registros,
                                         date(2026, 10, 21), date(2026, 11, 20), requisicion="REQ-123")
        reader = PdfReader(BytesIO(pdf))
        self.assertIn("Listado de ODT", reader.pages[0].extract_text())
        self.assertNotIn("Resumen de servicios", reader.pages[0].extract_text())
        self.assertNotIn("Historial de acciones por ODT", reader.pages[0].extract_text())
        self.assertIn("Historial de acciones por ODT", reader.pages[1].extract_text())
