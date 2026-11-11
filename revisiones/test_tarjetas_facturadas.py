from datetime import date
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth.models import User
from django.test import TestCase, RequestFactory
from django.template import engines
from .models import ODT
from .facturacion_models import PeriodoFacturacion, FacturacionContratista, FacturacionODT
from .detalle_facturacion import detalle_facturacion


class TarjetasServiciosFacturadosTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("admin", password="test")
        periodo = PeriodoFacturacion.objects.create(fecha_desde=date(2026, 9, 21), fecha_hasta=date(2026, 10, 20))
        self.facturacion = FacturacionContratista.objects.create(periodo=periodo, contratista="Prueba", numero_requisicion="REQ")

    def contexto(self):
        req = RequestFactory().get("/")
        req.user = self.user
        with patch("revisiones.detalle_facturacion.render", side_effect=lambda r, t, c: c):
            return detalle_facturacion(req, self.facturacion.pk)

    def test_tarjetas_siempre_visibles_con_cero(self):
        context = self.contexto()
        for key in ("cantidad_renovacion", "monto_renovacion", "cantidad_preventivo", "monto_preventivo"):
            self.assertEqual(context[key], 0)
        template = engines["django"].get_template("revisiones/detalle_facturacion.html")
        with patch("django.urls.reverse", return_value="/test/"):
            html = template.render(context)
        self.assertIn("Renovación", html)
        self.assertIn("Mantenimiento preventivo", html)
        self.assertEqual(html.count("hist-tarjeta-resumen"), 9)

    def test_suma_valores_facturados_y_aliases(self):
        for n, servicio, monto in ((1, "MANTENIMIENTO RENOVACIÓN", 100), (2, "RENOVACION", 50),
                                  (3, "MANTENIMIENTO PREVENTIVO", 25), (4, "MANTENCION CORRECTIVA CON COBRO", 10)):
            odt = ODT.objects.create(numero=n, servicio="Servicio actual distinto")
            FacturacionODT.objects.create(facturacion=self.facturacion, odt=odt,
                                          servicio_facturado=servicio, monto_facturado=monto)
        context = self.contexto()
        self.assertEqual(context["cantidad_renovacion"], 2)
        self.assertEqual(context["monto_renovacion"], Decimal("150"))
        self.assertEqual(context["cantidad_preventivo"], 1)
        self.assertEqual(context["monto_preventivo"], Decimal("25"))
        self.assertEqual(context["monto_total"], Decimal("185"))
