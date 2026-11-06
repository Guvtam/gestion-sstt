from datetime import datetime, timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.template import engines
from django.test import TestCase, RequestFactory
from django.utils import timezone
from .models import ODT
from .analisis_odt import analisis_odt
from .indicadores_odt import con_indicadores_odt

class AnalisisODTTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_superuser("admin",password="test")
        self.base=timezone.now()-timedelta(days=7)
        for n, horas in ((1,24),(2,72)):
            ODT.objects.create(numero=n,cuenta_completa="FIR-100",contratista="Prueba",servicio="CORRECTIVO",
                fecha_creacion=self.base,fecha_finalizacion=self.base+timedelta(hours=horas),estado_softguard="Finalizado")
        ODT.objects.create(numero=3,cuenta_completa="FIR-200",fecha_creacion=self.base,estado_softguard="Pendiente")
        ODT.objects.create(numero=4,cuenta_completa="FIR-100",servicio="MANTENIMIENTO PREVENTIVO",
            fecha_creacion=self.base-timedelta(days=20),fecha_finalizacion=self.base-timedelta(days=19),estado_softguard="Finalizado")

    def consultar(self,**extra):
        req=RequestFactory().get("/",{"desde":(self.base-timedelta(days=1)).date().isoformat(),
                                      "hasta":timezone.localdate().isoformat(),**extra})
        req.user=self.user
        with patch("revisiones.analisis_odt.render",side_effect=lambda r,t,c:c):
            return analisis_odt(req)

    def test_metricas_y_denominador_sla(self):
        c=self.consultar()
        self.assertEqual(c["resumen"]["total"],3)
        self.assertEqual(c["resumen"]["cumple"],1)
        self.assertEqual(c["resumen"]["no_cumple"],1)
        self.assertEqual(c["resumen"]["pendiente"],1)
        self.assertEqual(c["resumen"]["porcentaje_sla"],50)
        self.assertEqual(c["resumen"]["recurrentes"],2)
        self.assertEqual(c["resumen"]["con_preventivo"],2)
        self.assertEqual(sum(x["cantidad"] for x in c["por_servicio"]),3)

    def test_filtro_detalle_no_altera_indicadores(self):
        c=self.consultar(vista="sla")
        self.assertEqual(c["resumen"]["total"],3)
        self.assertEqual([o.numero for o in c["pagina"]],[2])

    def test_fechas_invalidas_y_vacio(self):
        c=self.consultar(desde="invalida")
        self.assertTrue(c["errores"])
        self.assertEqual(c["resumen"]["total"],0)
        self.assertIsNone(c["resumen"]["porcentaje_sla"])

    def test_reglas_compartidas_y_fechas_negativas(self):
        ODT.objects.create(numero=5,fecha_creacion=self.base,fecha_finalizacion=self.base-timedelta(hours=1))
        self.assertEqual(con_indicadores_odt(ODT.objects.filter(numero=5)).get().estado_sla,"ERROR_FECHAS")

    def test_plantilla_y_enlaces(self):
        with patch("django.urls.reverse",return_value="/test/"):
            html=engines["django"].get_template("revisiones/analisis_odt.html").render(self.consultar())
        self.assertIn("Gestión de pagos",html)
        self.assertIn("numero_odt=1",html)
        self.assertIn("SLA pendiente",html)

    def test_permiso_restringido(self):
        self.user=get_user_model().objects.create_user("lectura")
        with self.assertRaises(PermissionDenied):
            self.consultar()

    def test_selecciones_graficas_actualizan_kpi_y_detalle(self):
        c=self.consultar(sla="CUMPLE")
        self.assertEqual(c["resumen"]["total"],1)
        self.assertEqual([o.numero for o in c["pagina"]],[1])
        c=self.consultar(preventivo="sin")
        self.assertEqual(c["resumen"]["total"],1)
        c=self.consultar(servicio="CORRECTIVO",recurrencia="con")
        self.assertEqual(c["resumen"]["total"],2)
        self.assertEqual(sum(i["cantidad"] for i in c["por_estado"]),2)

    def test_enlaces_conservan_filtros_y_reinician_paginacion(self):
        from urllib.parse import urlsplit,parse_qs
        c=self.consultar(q="FIR-100",page="2",estado="Finalizado")
        url=c["por_servicio"][0]["url"]
        parametros=parse_qs(urlsplit(url).query)
        self.assertEqual(parametros["estado"],["Finalizado"])
        self.assertEqual(parametros["q"],["FIR-100"])
        self.assertNotIn("page",parametros)
        self.assertIn("servicio",parametros)
        parametros=parse_qs(urlsplit(c["por_estado"][0]["url"]).query,keep_blank_values=True)
        self.assertEqual(parametros["estado"],[""])

    def test_datos_graficas_concilian_y_tendencia_filtra_periodo(self):
        c=self.consultar()
        self.assertEqual(sum(p["cantidad"] for p in c["sla_grafico"]), c["resumen"]["total"])
        self.assertEqual(sum(p["cantidad"] for p in c["preventivos_grafico"]), c["resumen"]["total"])
        self.assertEqual(sum(p["cantidad"] for p in c["recurrencias_grafico"]), c["resumen"]["total"])
        self.assertEqual(sum(p["cantidad"] for p in c["tendencia"]), c["resumen"]["total"])
        self.assertIn("desde=", c["tendencia"][0]["url"])
        self.assertTrue(self.consultar(desde="")["tendencia_mensual"])

    def test_dashboard_vacio_sin_porcentajes_invalidos(self):
        c=self.consultar(q="no-existe")
        self.assertEqual(c["resumen"]["total"],0)
        self.assertEqual(c["donut_fondo"],"#e6edf5")
        self.assertEqual(c["tendencia"],[])
