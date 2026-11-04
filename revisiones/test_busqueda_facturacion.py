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
        return [item.odt.numero for f in context["resultados_busqueda"] for item in f.items.select_related("odt").order_by("odt__numero")]

    def test_odt_exacta_con_formato(self):
        self.assertEqual(self.numeros(self.buscar(buscar_odt="77.527")), [77527, 77528])
        self.assertEqual(self.numeros(self.buscar(buscar_odt="77 527")), [77527, 77528])

    def test_requisicion_parcial_sin_distinguir_mayusculas(self):
        self.assertEqual(self.numeros(self.buscar(buscar_requisicion="abc")), [77527, 77528])

    def test_campos_combinados(self):
        self.assertEqual(self.numeros(self.buscar(buscar_odt="77527", buscar_requisicion="XYZ")), [])

    def test_periodo_y_totales_no_cambian(self):
        context = self.buscar(buscar_odt="77527", periodo=str(self.periodos[0].pk))
        self.assertEqual(self.numeros(context), [77527, 77528])
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

    def test_una_fila_por_facturacion_y_conteo_total_al_buscar_una_odt(self):
        context = self.buscar(buscar_odt="77527")
        filas = list(context["resultados_busqueda"])
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0].cantidad_odt, 2)
        self.assertEqual(filas[0].numero_requisicion, "REQ-ABC-100")

    def test_requisicion_repetida_no_mezcla_periodos(self):
        FacturacionContratista.objects.update(numero_requisicion="MISMA")
        context = self.buscar(buscar_requisicion="MISMA")
        filas = list(context["resultados_busqueda"])
        self.assertEqual(len(filas), 2)
        self.assertEqual(sorted(f.cantidad_odt for f in filas), [1, 2])

    def test_accion_abre_detalle_de_la_facturacion_completa(self):
        context = self.buscar(buscar_odt="77527")
        facturacion = context["resultados_busqueda"][0]
        template = engines["django"].get_template("revisiones/historial_facturacion.html")
        with patch("django.urls.reverse", side_effect=lambda name, args=None, kwargs=None, **rest: (
                "/detalle/" + str(args[0]) + "/" if name == "detalle_facturacion" else "/test/")):
            html = template.render(context)
        self.assertIn('href="/detalle/' + str(facturacion.pk) + '/">Ver todas las ODT de la facturación</a>', html)
        self.assertIn("Cantidad total de ODT", html)

    def test_busqueda_odt_enlaza_orden_exacta_sin_filtros_de_fecha(self):
        context = self.buscar(buscar_odt="77.527")
        self.assertEqual(context["numero_odt_buscada"], 77527)
        template = engines["django"].get_template("revisiones/historial_facturacion.html")
        with patch("django.urls.reverse", return_value="/bandeja/"):
            html = template.render(context)
        self.assertIn('numero_odt=77527&amp;estado=&amp;fecha_desde=&amp;fecha_hasta=', html)
        self.assertNotIn("Ver información y acciones de ODT", html)
        self.assertIn("Ver todas las ODT de la facturación", html)

    def test_busqueda_requisicion_conserva_enlace_grupal(self):
        context = self.buscar(buscar_requisicion="ABC")
        self.assertIsNone(context["numero_odt_buscada"])
        template = engines["django"].get_template("revisiones/historial_facturacion.html")
        with patch("django.urls.reverse", return_value="/test/"):
            html = template.render(context)
        self.assertNotIn("ODT encontrada", html)
        self.assertNotIn("Ver información y acciones de ODT", html)
