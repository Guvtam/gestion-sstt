from datetime import date
from unittest.mock import patch
from django.contrib.auth.models import User
from django.template import engines
from django.test import RequestFactory, TestCase
from .models import ODT
from .facturacion_models import PeriodoFacturacion, FacturacionContratista, FacturacionODT
from .historial_facturacion import historial_facturacion


class BusquedaFacturacionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("admin", password="test")
        self.factory = RequestFactory()
        self.periodos = []
        for mes, requisicion, numeros in ((8, "REQ-ABC-100", (77527, 77528)), (9, "REQ-XYZ-200", (80000,))):
            periodo = PeriodoFacturacion.objects.create(fecha_desde=date(2026, mes, 21), fecha_hasta=date(2026, mes+1, 20))
            self.periodos.append(periodo)
            f = FacturacionContratista.objects.create(periodo=periodo, contratista="Contratista", numero_requisicion=requisicion)
            for n in numeros:
                odt = ODT.objects.create(numero=n)
                FacturacionODT.objects.create(facturacion=f, odt=odt, servicio_facturado="Preventivo", monto_facturado=100)

    def buscar(self, **datos):
        request = self.factory.get("/", datos)
        request.user = self.user
        with patch("revisiones.historial_facturacion.render", side_effect=lambda r, t, c: c):
            return historial_facturacion(request)

    def numeros(self, context):
        return [i.odt.numero for i in context["resultados_busqueda"]]

    def test_odt_exacta_con_formato(self):
        self.assertEqual(self.numeros(self.buscar(buscar_odt="77.527")), [77527])
        self.assertEqual(self.numeros(self.buscar(buscar_odt="77 527")), [77527])

    def test_requisicion_parcial_sin_distinguir_mayusculas(self):
        self.assertEqual(self.numeros(self.buscar(buscar_requisicion="abc")), [77527, 77528])

    def test_campos_combinados(self):
        self.assertEqual(self.numeros(self.buscar(buscar_odt="77527", buscar_requisicion="XYZ")), [])

    def test_periodo_y_totales_no_cambian(self):
        context = self.buscar(buscar_odt="77527", periodo=str(self.periodos[0].pk))
        self.assertEqual(self.numeros(context), [77527])
        self.assertEqual(context["resumen_costos"]["cantidad"], 2)
        self.assertEqual(context["facturaciones"][0].cantidad_odt, 2)
        self.assertEqual(self.numeros(self.buscar(buscar_odt="77527", periodo=str(self.periodos[1].pk))), [])

    def test_entrada_invalida_o_sin_resultados(self):
        context = self.buscar(buscar_odt="abc")
        self.assertTrue(context["error_busqueda"])
        self.assertEqual(self.numeros(context), [])
        self.assertEqual(self.numeros(self.buscar(buscar_odt="999")), [])

    def test_sin_busqueda_conserva_historial(self):
        context = self.buscar()
        self.assertFalse(context["busqueda_activa"])
        self.assertEqual(len(context["periodos"]), 2)

    def test_plantilla_compila_y_conserva_busqueda(self):
        template = engines["django"].get_template("revisiones/historial_facturacion.html")
        context = self.buscar(buscar_odt="77527")
        with patch("django.urls.reverse", return_value="/test/"):
            html = template.render(context)
        self.assertIn('name="buscar_odt"', html)
        self.assertIn('name="buscar_requisicion"', html)
        self.assertIn("REQ-ABC-100", html)
