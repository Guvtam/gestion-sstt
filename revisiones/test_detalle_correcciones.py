from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth.models import User
from django.template import engines
from django.test import RequestFactory, TestCase
from .models import ODT, CorreccionODT
from .estadisticas_correcciones import estadisticas_correcciones


class DetalleCorreccionesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("admin", password="test")
        self.factory = RequestFactory()
        for n, monto, servicio, estado in ((1, True, False, "PENDIENTE"), (2, False, True, "EN_PROCESO"), (3, True, True, "ACTUALIZADA")):
            odt = ODT.objects.create(numero=n, servicio="Original", valor_pago_tecnico=100, contratista="Prueba")
            CorreccionODT.objects.create(odt=odt, corrige_monto=monto, corrige_servicio=servicio,
                                        monto_objetivo=80, servicio_objetivo="Nuevo", estado=estado)

    def consultar(self, **datos):
        request = self.factory.get("/", datos)
        request.user = self.user
        def coordinador(n):
            return {"usuario": "rsilva" if n != 3 else None, "nombre": "Romina Silva" if n != 3 else "Sin identificar"}
        with patch("revisiones.estadisticas_correcciones.identificar_coordinador_odt", side_effect=coordinador), \
             patch("revisiones.estadisticas_correcciones.render", side_effect=lambda r, t, c: c):
            return estadisticas_correcciones(request)

    def test_listado_coincide_con_indicadores(self):
        context = self.consultar()
        self.assertEqual(context["pagina_detalle"].paginator.count, context["total"]["cantidad"])
        self.assertEqual([r["numero"] for r in context["pagina_detalle"]], [1,2,3])
        self.assertEqual(context["pagina_detalle"][0]["diferencia"], Decimal("-20"))
        self.assertEqual(context["pagina_detalle"][1]["estado"], "Procesado")
        self.assertEqual(context["pagina_detalle"][2]["estado"], "Actualizado")

    def test_filtros_se_aplican_a_listado_y_resumen(self):
        context = self.consultar(coordinador="rsilva", tipo="MONTO", estado="PENDIENTE")
        self.assertEqual(context["total"]["cantidad"], 1)
        self.assertEqual([r["numero"] for r in context["pagina_detalle"]], [1])

    def test_sin_resultados(self):
        context = self.consultar(coordinador="rsilva", tipo="AMBOS")
        self.assertEqual(context["pagina_detalle"].paginator.count, 0)
        self.assertEqual(context["total"]["cantidad"], 0)

    def test_plantilla_contiene_detalle_y_enlace_exacto(self):
        template = engines["django"].get_template("revisiones/estadisticas_correcciones.html")
        with patch("django.urls.reverse", return_value="/test/"):
            html = template.render(self.consultar())
        self.assertIn("Detalle de ODT modificadas", html)
        self.assertIn("numero_odt=1&amp;estado=&amp;fecha_desde=&amp;fecha_hasta=", html)

    def test_paginacion_conserva_filtros(self):
        for n in range(4,56):
            odt = ODT.objects.create(numero=n)
            CorreccionODT.objects.create(odt=odt, corrige_monto=True)
        context = self.consultar(coordinador="rsilva", page="2")
        self.assertEqual(context["pagina_detalle"].number, 2)
        self.assertEqual(len(context["pagina_detalle"]), 4)
        self.assertEqual(context["pagina_detalle"].paginator.count, context["total"]["cantidad"])
        self.assertEqual(context["query_detalle"], "coordinador=rsilva")
