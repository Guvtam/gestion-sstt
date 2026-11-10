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
            request = RequestFactory().get("/analisis-odt/")
            request.user = self.user
            html=engines["django"].get_template("revisiones/analisis_odt.html").render({**self.consultar(), "request": request})
        self.assertIn("Gestión de pagos",html)
        self.assertIn("<td>1</td>",html)
        self.assertNotIn("numero_odt=",html)
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
        from .consultas.preventivos import asignar_ultimos_preventivos
        actuales={o.pk:o for o in asignar_ultimos_preventivos(con_indicadores_odt(base))}
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

    def test_ranking_agrupa_codigo_cuenta_y_cuenta_solo_periodo_filtrado(self):
        ODT.objects.create(numero=600, cuenta_completa="FIR-100 - Nombre actualizado", contratista="Otro",
            servicio="MANTENCION CORRECTIVA CON COBRO", estado_softguard="Finalizado",
            fecha_creacion=self.base, fecha_finalizacion=self.base+timedelta(hours=4))
        ODT.objects.create(numero=601, cuenta_completa="", servicio="MANTENCION CORRECTIVA CON COBRO",
            estado_softguard="Finalizado", fecha_finalizacion=self.base)
        contexto = self.consultar()
        self.assertEqual([(r["cuenta"], r["cantidad"]) for r in contexto["ranking_cuentas"]], [("FIR-100", 3)])
        self.assertEqual(contexto["ranking_cuentas"][0]["ancho"], "100.00")
        # La preventiva histórica de esta cuenta queda fuera del período.
        self.assertEqual(contexto["resumen"]["total"], 4)

    def test_ranking_top_diez_y_empates_estables(self):
        for i in range(12):
            ODT.objects.create(numero=700+i, cuenta_completa=f"FIR-{300+i}",
                servicio="MANTENCION CORRECTIVA CON COBRO", estado_softguard="Finalizado",
                fecha_creacion=self.base, fecha_finalizacion=self.base+timedelta(hours=4))
        ranking = self.consultar()["ranking_cuentas"]
        self.assertEqual(len(ranking), 10)
        self.assertEqual(ranking[0]["cuenta"], "FIR-100")
        self.assertEqual([r["cuenta"] for r in ranking[1:]], [f"FIR-{300+i}" for i in range(9)])
        self.assertEqual([r["posicion"] for r in ranking], list(range(1, 11)))

    def test_ranking_seleccion_exacta_chip_y_limpieza_conservan_multiservicio(self):
        from urllib.parse import parse_qs, urlsplit
        ODT.objects.create(numero=800, cuenta_completa="FIR-1000", servicio="MANTENCION CORRECTIVA CON COBRO",
            estado_softguard="Finalizado", fecha_creacion=self.base, fecha_finalizacion=self.base+timedelta(hours=4))
        servicios = ["MANTENCION CORRECTIVA CON COBRO", "MANTENIMIENTO PREVENTIVO"]
        contexto = self.consultar(cuenta="FIR-100", servicios=servicios, page="2", servicios_filtrados="1")
        self.assertEqual(contexto["resumen"]["total"], 2)
        self.assertEqual({o.numero for o in contexto["pagina"]}, {1, 2})
        self.assertTrue(contexto["ranking_cuentas"][0]["activo"])
        params = parse_qs(urlsplit(contexto["ranking_cuentas"][0]["url"]).query)
        self.assertNotIn("cuenta", params)
        self.assertNotIn("page", params)
        self.assertEqual(params["servicios"], servicios)
        self.assertTrue(any(f["nombre"] == "Cuenta: FIR-100" for f in contexto["filtros_activos"]))
        self.assertNotIn("cuenta", parse_qs(urlsplit(contexto["quitar_selecciones"]).query))
        self.assertEqual(self.consultar(cuenta="FIR-inexistente")["ranking_cuentas"], [])

    def test_ranking_respeta_servicio_efectivo_sla_y_detalle_no_modifica_ranking(self):
        ODT.objects.filter(numero=2).update(servicio_editado="MANTENIMIENTO PREVENTIVO")
        contexto = self.consultar(servicios_filtrados="1", servicios=["MANTENCION CORRECTIVA CON COBRO"])
        self.assertEqual(contexto["ranking_cuentas"][0]["cantidad"], 1)
        self.assertEqual(self.consultar(sla="NO_CUMPLE")["ranking_cuentas"][0]["cantidad"], 1)
        self.assertEqual(self.consultar(vista="sla")["ranking_cuentas"][0]["cantidad"], 2)

    def test_ranking_plantilla_y_estado_vacio(self):
        contexto = self.consultar(cuenta="FIR-100")
        with patch("django.urls.reverse", return_value="/test/"):
            html = engines["django"].get_template("revisiones/analisis_odt.html").render(contexto)
        self.assertIn("Ranking de cuentas con más incidencias", html)
        self.assertIn('name="cuenta" value="FIR-100"', html)
        self.assertIn("2 ODT", html)
        self.assertIn('aria-label="FIR-100: 2 incidencias. Filtrar cuenta"', html)
        self.assertEqual(self.consultar(desde="fecha-invalida")["ranking_cuentas"], [])


    def test_detalle_muestra_servicio_y_monto_efectivos_en_clp(self):
        from decimal import Decimal
        ODT.objects.filter(numero=1).update(valor_pago_tecnico=12345)
        ODT.objects.filter(numero=2).update(valor_pago_tecnico=9000, valor_pago_editado=25000,
                                          servicio_editado="MANTENIMIENTO PREVENTIVO")
        contexto = self.consultar()
        montos = {o.numero: o.monto_efectivo for o in contexto["pagina"]}
        self.assertEqual(montos, {1: Decimal("12345"), 2: Decimal("25000")})
        with self.assertNumQueries(0), patch("django.urls.reverse", return_value="/test/"):
            html = engines["django"].get_template("revisiones/analisis_odt.html").render(contexto)
        self.assertIn("<th>Servicio</th><th>Monto CLP</th>", html)
        self.assertIn("$12.345", html)
        self.assertIn("$25.000", html)
        self.assertIn("MANTENIMIENTO PREVENTIVO", html)
        self.assertNotIn("$9.000", html)

    def test_detalle_respeta_monto_editado_cero_y_vacio_once_columnas(self):
        ODT.objects.filter(numero=1).update(valor_pago_tecnico=50000, valor_pago_editado=0)
        contexto = self.consultar()
        self.assertEqual(next(o.monto_efectivo for o in contexto["pagina"] if o.numero == 1), 0)
        with patch("django.urls.reverse", return_value="/test/"):
            html = engines["django"].get_template("revisiones/analisis_odt.html").render(contexto)
            vacio = engines["django"].get_template("revisiones/analisis_odt.html").render(self.consultar(q="inexistente"))
        self.assertIn("$0", html)
        self.assertNotIn("$50.000", html)
        self.assertIn('colspan="11"', vacio)


    def test_detalle_odt_texto_y_historial_con_modal_compartido(self):
        from django.urls import reverse
        self.client.force_login(self.user)
        respuesta = self.client.get(reverse("analisis_odt"), {
            "desde": (self.base-timedelta(days=1)).date().isoformat(),
            "hasta": timezone.localdate().isoformat(),
        })
        self.assertContains(respuesta, "<td>1</td>")
        self.assertNotContains(respuesta, "numero_odt=")
        self.assertContains(respuesta, "<th>Historial</th>")
        self.assertContains(respuesta, 'class="btn-historial-odt alt"', count=2)
        self.assertContains(respuesta, f'data-url="{reverse("historial_odt", args=[1])}"')
        for identificador in ("modalHistorial", "historialNumero", "historialContenido", "cerrarHistorial"):
            self.assertContains(respuesta, f'id="{identificador}"', count=1)
        self.assertContains(respuesta, "historial_facturacion_odt.js")

    def test_analisis_sin_permiso_historial_no_muestra_control_activo(self):
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType
        from django.urls import reverse
        usuario = get_user_model().objects.create_user("revisor_sin_historial")
        for codigo in ("ver_bandeja_sstt", "revisar_pago_sstt"):
            permiso, _ = Permission.objects.get_or_create(content_type=ContentType.objects.get_for_model(ODT), codename=codigo)
            usuario.user_permissions.add(permiso)
        self.client.force_login(usuario)
        respuesta = self.client.get(reverse("analisis_odt"), {"desde":"", "hasta":""})
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Sin permiso")
        self.assertNotContains(respuesta, 'id="modalHistorial"')
        self.assertNotContains(respuesta, 'class="btn-historial-odt alt"')


    def test_detalle_siempre_visible_sin_desplegable(self):
        with patch("django.urls.reverse", return_value="/test/"):
            html = engines["django"].get_template("revisiones/analisis_odt.html").render(self.consultar())
        self.assertIn('<div class="dashboard-detalle"><h2>Detalle de ODT', html)
        self.assertNotIn('<details class="dashboard-detalle"', html)
        self.assertNotIn("abrir / cerrar", html)
        self.assertIn("<td>1</td>", html)
