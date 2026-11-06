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
            ODT.objects.create(numero=n,cuenta_completa="FIR-100",contratista="Prueba",servicio="MANTENCION CORRECTIVA CON COBRO",
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
        self.assertEqual(c["resumen"]["total"],2)
        self.assertEqual(c["resumen"]["cumple"],1)
        self.assertEqual(c["resumen"]["no_cumple"],1)
        self.assertEqual(c["resumen"]["pendiente"],0)
        self.assertEqual(c["resumen"]["porcentaje_sla"],50)
        self.assertEqual(c["resumen"]["recurrentes"],2)
        self.assertEqual(c["resumen"]["con_preventivo"],2)
        self.assertEqual(sum(x["cantidad"] for x in c["por_servicio"]),2)

    def test_filtro_detalle_no_altera_indicadores(self):
        c=self.consultar(vista="sla")
        self.assertEqual(c["resumen"]["total"],2)
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
        self.assertIn("Cumplimiento SLA",html)
        self.assertNotIn("Distribución de ODT por estado",html)

    def test_permiso_restringido(self):
        self.user=get_user_model().objects.create_user("lectura")
        with self.assertRaises(PermissionDenied):
            self.consultar()

    def test_selecciones_graficas_actualizan_kpi_y_detalle(self):
        c=self.consultar(sla="CUMPLE")
        self.assertEqual(c["resumen"]["total"],1)
        self.assertEqual([o.numero for o in c["pagina"]],[1])
        c=self.consultar(preventivo="sin")
        self.assertEqual(c["resumen"]["total"],0)
        c=self.consultar(servicio="MANTENCION CORRECTIVA CON COBRO",recurrencia="con")
        self.assertEqual(c["resumen"]["total"],2)
        self.assertEqual(sum(i["cantidad"] for i in c["por_servicio"]),2)

    def test_enlaces_conservan_filtros_y_reinician_paginacion(self):
        from urllib.parse import urlsplit,parse_qs
        c=self.consultar(q="FIR-100",page="2",estado="Finalizado")
        url=c["por_servicio"][0]["url"]
        parametros=parse_qs(urlsplit(url).query)
        self.assertNotIn("estado",parametros)
        self.assertEqual(parametros["q"],["FIR-100"])
        self.assertNotIn("page",parametros)
        self.assertIn("servicio",parametros)

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

    def test_solo_finalizadas_y_rango_por_finalizacion_sin_opcion_de_anularlo(self):
        ODT.objects.create(numero=10,estado_softguard="Asignado",fecha_creacion=self.base,
                           fecha_finalizacion=self.base+timedelta(hours=10))
        ODT.objects.create(numero=11,estado_softguard="Finalizado",servicio="MANTENCION CORRECTIVA CON COBRO",
            fecha_creacion=self.base-timedelta(days=90),fecha_finalizacion=self.base+timedelta(hours=10))
        c=self.consultar(campo="creacion",estado="Pendiente")
        self.assertEqual({o.numero for o in c["pagina"]},{1,2,11})
        self.assertEqual(c["campo"],"finalizacion")

    def test_metricas_en_tres_consultas_independientes_de_numero_de_odt(self):
        for cantidad in (0,100):
            if cantidad:
                ODT.objects.bulk_create([ODT(numero=100+n,estado_softguard="Finalizado",servicio="MANTENCION CORRECTIVA CON COBRO",
                    fecha_creacion=self.base,fecha_finalizacion=self.base+timedelta(hours=24),
                    cuenta_completa="FIR-100",contratista="Prueba") for n in range(cantidad)])
            with self.assertNumQueries(3):
                contexto=self.consultar()
            self.assertEqual(contexto["resumen"]["total"],2+cantidad)

    def test_sla_porcentajes_excluyen_fechas_invalidas(self):
        ODT.objects.create(numero=20,estado_softguard="Finalizado",servicio="MANTENCION CORRECTIVA CON COBRO",fecha_creacion=None,fecha_finalizacion=self.base)
        c=self.consultar()
        self.assertEqual(c["resumen"]["revisar_fechas"],1)
        self.assertEqual([g["porcentaje"] for g in c["sla_grafico"]],[50,50])
        self.assertEqual(c["resumen"]["porcentaje_sla"],50)

    def test_metricas_rapidas_equivalen_a_reglas_de_bandeja(self):
        from .metricas_analisis import cargar_metricas
        base=ODT.objects.filter(numero__in=[1,2,3,4])
        actuales={o.pk:o for o in con_indicadores_odt(base)}
        for o in cargar_metricas(base):
            anterior=actuales[o.pk]
            self.assertEqual(o.estado_sla,anterior.estado_sla)
            self.assertEqual(o.cantidad_incidencias,anterior.cantidad_incidencias)
            self.assertEqual(o.fecha_ultimo_preventivo,anterior.fecha_ultimo_preventivo)

    def test_servicios_predeterminados_iguales_bandeja_y_seleccion_explicita(self):
        from .views import SERVICIOS_PRINCIPALES
        ODT.objects.create(numero=30,estado_softguard="Finalizado",servicio="MARCHA BLANCA",
            fecha_creacion=self.base,fecha_finalizacion=self.base+timedelta(hours=2))
        c=self.consultar()
        self.assertEqual(c["servicios_seleccionados"],list(SERVICIOS_PRINCIPALES))
        self.assertEqual(c["resumen"]["total"],2)
        c=self.consultar(servicios_filtrados="1",servicios=["MARCHA BLANCA"])
        self.assertEqual(c["resumen"]["total"],1)
        self.assertEqual([o.numero for o in c["pagina"]],[30])
        c=self.consultar(servicios_filtrados="1")
        self.assertEqual(c["resumen"]["total"],0)

    def test_enlaces_de_graficos_conservan_servicios_multiple(self):
        from urllib.parse import parse_qs,urlsplit
        c=self.consultar(servicios_filtrados="1",servicios=["MANTENCION CORRECTIVA CON COBRO","MANTENIMIENTO PREVENTIVO"])
        params=parse_qs(urlsplit(c["sla_grafico"][0]["url"]).query)
        self.assertEqual(params["servicios"],["MANTENCION CORRECTIVA CON COBRO","MANTENIMIENTO PREVENTIVO"])

    def test_grafico_cuenta_cuentas_unicas_en_categorias_exclusivas(self):
        ODT.objects.all().delete()
        numero=1000
        for codigo,cantidad in (("FIR-200",2),("FIR-300",3),("FIR-400",5)):
            for i in range(cantidad):
                numero+=1
                ODT.objects.create(numero=numero,cuenta_completa=codigo+" - "+str(i),
                    contratista="Proveedor "+str(i),servicio="MANTENCION CORRECTIVA CON COBRO",
                    fecha_creacion=self.base,fecha_finalizacion=self.base+timedelta(hours=1),
                    estado_softguard="Finalizado")
        c=self.consultar()
        self.assertEqual([g["cantidad"] for g in c["incidencias_grafico"]],[1,1,1])
        self.assertEqual(c["cuentas_repetidas"],3)
        self.assertTrue(all("incidencias_cuenta=" in g["url"] for g in c["incidencias_grafico"]))
        c=self.consultar(incidencias_cuenta="3")
        self.assertEqual(c["resumen"]["total"],3)
        self.assertEqual({o.clave_cuenta_analisis for o in c["pagina"]},{"FIR-300"})

    def test_incidencias_cuenta_solo_finalizadas_en_90_dias(self):
        ODT.objects.all().delete()
        for n,dias,estado in ((100,5,"Finalizado"),(101,6,"Finalizado"),(102,95,"Finalizado"),(103,5,"Pendiente")):
            ODT.objects.create(numero=n,cuenta_completa="FIR-500",contratista="",
                servicio="MANTENCION CORRECTIVA CON COBRO",fecha_creacion=self.base-timedelta(days=dias),
                fecha_finalizacion=timezone.now()-timedelta(days=dias),estado_softguard=estado)
        c=self.consultar()
        self.assertEqual(c["incidencias_grafico"][0]["cantidad"],1)
        self.assertEqual({o.incidencias_cuenta_90 for o in c["pagina"]},{2})
        self.assertEqual({o.cantidad_incidencias for o in c["pagina"]},{0})
