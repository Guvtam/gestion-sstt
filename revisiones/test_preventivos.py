from datetime import datetime
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.template import engines
from django.test import RequestFactory, TestCase
from django.utils import timezone
from .models import ODT, CatalogoCuenta
from .mantenimientos_preventivos import mantenimientos_preventivos


class PreventivosCuentasTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("admin", password="test")
        self.factory = RequestFactory()
        CatalogoCuenta.objects.create(codigo_cuenta="FIR-100", nombre_cuenta="Cliente B2B", tipo_cliente="B2B")
        CatalogoCuenta.objects.create(codigo_cuenta="FIR-200", nombre_cuenta="Sin preventivos", tipo_cliente="B2C")
        for numero, estado, dia in ((1, "Finalizado", 1), (2, "Finalizado", 5), (3, "Pendiente", 10)):
            ODT.objects.create(numero=numero, cuenta_completa="fir - 100 - Cliente B2B",
                               servicio="MANTENIMIENTO PREVENTIVO", estado_softguard=estado,
                               fecha_finalizacion=timezone.make_aware(datetime(2026, 10, dia)), tecnico="Técnico")

    def consultar(self, **params):
        req = self.factory.get("/", params)
        req.user = self.user
        with patch("revisiones.mantenimientos_preventivos.render", side_effect=lambda r,t,c:c):
            return mantenimientos_preventivos(req)

    def test_ultimo_finalizado_y_cuentas_sin_preventivo(self):
        context = self.consultar()
        cuentas = {c["codigo"]: c for c in context["pagina"]}
        self.assertEqual(cuentas["FIR-100"]["ultimo"].numero, 2)
        self.assertEqual(cuentas["FIR-100"]["cantidad"], 3)
        self.assertEqual(cuentas["FIR-100"]["pendientes"], 1)
        self.assertIsNone(cuentas["FIR-200"]["ultimo"])
        self.assertEqual(context["sin_preventivo"], 1)

    def test_filtros_y_busqueda(self):
        self.assertEqual(self.consultar(situacion="SIN_PREVENTIVO")["total_cuentas"], 1)
        self.assertEqual(self.consultar(q="Cliente B2B")["total_cuentas"], 1)
        self.assertEqual(self.consultar(situacion="PENDIENTES")["total_cuentas"], 1)

    def test_detalle_solo_cuenta_seleccionada(self):
        context = self.consultar(cuenta="FIR-100")
        self.assertEqual({o.numero for o in context["pagina_detalle"]}, {1,2,3})
        self.assertEqual(self.consultar(cuenta="FIR-200")["pagina_detalle"].paginator.count, 0)

    def test_servicio_corregido_y_cuenta_sin_catalogo(self):
        ODT.objects.create(numero=4, cuenta_completa="FIR-300 - Nueva cuenta", servicio="Correctiva",
                           servicio_editado="MANTENIMIENTO PREVENTIVO", estado_softguard="Finalizado",
                           fecha_finalizacion=timezone.now())
        context = self.consultar(cuenta="FIR-300")
        self.assertEqual(context["cuenta_seleccionada"]["ultimo"].numero, 4)

    def test_preventivo_corregido_a_otro_servicio_no_se_cuenta(self):
        ODT.objects.filter(numero=2).update(servicio_editado="MANTENCION CORRECTIVA CON COBRO")
        context = self.consultar(cuenta="FIR-100")
        self.assertEqual(context["cuenta_seleccionada"]["ultimo"].numero, 1)
        self.assertEqual(context["pagina_detalle"].paginator.count, 2)

    def test_usuario_sin_permiso_denegado(self):
        req = self.factory.get("/")
        req.user = User.objects.create_user("sinpermiso")
        with self.assertRaises(PermissionDenied):
            mantenimientos_preventivos(req)

    def test_plantilla_y_enlaces(self):
        with patch("django.urls.reverse", return_value="/test/"):
            html = engines["django"].get_template("revisiones/mantenimientos_preventivos.html").render(self.consultar(cuenta="FIR-100"))
        self.assertIn("Preventivos de FIR-100", html)
        self.assertIn("numero_odt=2", html)
        bandeja = engines["django"].get_template("revisiones/bandeja.html").template.source
        self.assertLess(bandeja.index("Mantenimientos preventivos</a>"), bandeja.index("Análisis por coordinador"))
