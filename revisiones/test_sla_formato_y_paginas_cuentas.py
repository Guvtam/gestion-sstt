from datetime import datetime, timedelta
from html import unescape
import re
from urllib.parse import parse_qs, urlsplit

from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.test import SimpleTestCase

from .dominio.indicadores import estado_sla
from .models import ODT
from .templatetags.formato_sstt import tiempo_sla


class TiempoSLATests(SimpleTestCase):
    def test_horas_y_minutos_hasta_24_horas(self):
        for valor, esperado in ((0,"0 h 0 min"),(59,"0 h 0 min"),(3600,"1 h 0 min"),
                                (86399,"23 h 59 min"),(86400,"24 h 0 min")):
            self.assertEqual(tiempo_sla(timedelta(seconds=valor)), esperado)

    def test_mas_de_24_desglosa_dias_sin_perder_minutos(self):
        for valor, esperado in ((86401,"1 día 0 h"),(90000,"1 día 1 h"),
                                (172800,"2 días 0 h"),(178200,"2 días 1 h 30 min"),
                                (864000,"10 días 0 h")):
            self.assertEqual(tiempo_sla(timedelta(seconds=valor)), esperado)

    def test_sin_datos_y_duraciones_invalidas_no_muestran_tiempos(self):
        for valor in (None,"",-1,timedelta(seconds=-1),"NaN","Infinity","invalido"):
            self.assertEqual(tiempo_sla(valor), "")

    def test_formato_no_cambia_el_limite_de_cumplimiento(self):
        inicio = datetime(2026,11,1)
        self.assertEqual(estado_sla(inicio,inicio+timedelta(hours=48)),"CUMPLE")
        self.assertEqual(tiempo_sla(timedelta(hours=48)),"2 días 0 h")
        self.assertEqual(estado_sla(inicio,inicio+timedelta(hours=48,seconds=1)),"NO_CUMPLE")
        self.assertEqual(estado_sla(inicio,inicio-timedelta(seconds=1)),"ERROR_FECHAS")

    def test_bandeja_y_analisis_muestran_el_mismo_tiempo_sin_javascript(self):
        odt = ODT(numero=55,cuenta_completa="FIR-55",servicio="MANTENIMIENTO PREVENTIVO")
        odt.estado_sla="NO_CUMPLE"
        odt.duracion_sla=timedelta(hours=53,minutes=20)
        datos={"registros":[odt],"pagina":Paginator([odt],50).get_page(1),"bandeja_url":"bandeja","filtros":{},
               "perms":{"revisiones":{"revisar_pago_sstt":True}}}
        for plantilla in ("bandeja","analisis_odt"):
            html = render_to_string("revisiones/"+plantilla+".html",datos)
            self.assertIn("2 días 5 h 20 min",html)
            self.assertIn("No cumple",html)
        odt.duracion_sla=timedelta(0)
        odt.estado_sla="CUMPLE"
        self.assertIn("0 h 0 min",render_to_string("revisiones/bandeja.html",datos))


class PaginasCuentasTests(SimpleTestCase):
    def test_numeros_arriba_y_abajo_conservan_filtros(self):
        pagina=Paginator(range(250),50).get_page(3)
        html=render_to_string("revisiones/administrar_cuentas.html",{
            "pagina":pagina,"cuentas":[],"estado_ceco":"sin","tipo":"B2C",
            "querystring":"q=Cliente&estado_ceco=sin&tipo=B2C&pendientes=1",
        })
        self.assertIn('aria-label="Paginación superior de cuentas"',html)
        self.assertIn('aria-label="Paginación inferior de cuentas"',html)
        self.assertEqual(html.count('aria-label="Página 3 actual"'),2)
        for numero in (1,2,4,5):
            self.assertEqual(html.count(f'aria-label="Ir a página {numero}"'),2)
        enlaces=re.findall(r'href="([^"]+)" aria-label="Ir a página [0-9]+"',html)
        self.assertTrue(enlaces)
        for enlace in enlaces:
            parametros=parse_qs(urlsplit(unescape(enlace)).query)
            self.assertEqual(parametros["estado_ceco"],["sin"])
            self.assertEqual(parametros["tipo"],["B2C"])
            self.assertEqual(parametros["q"],["Cliente"])
            self.assertEqual(parametros["pendientes"],["1"])
            self.assertEqual(len(parametros["page"]),1)
