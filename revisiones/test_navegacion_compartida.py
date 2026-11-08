from html import unescape
from urllib.parse import urlsplit, parse_qs
import re

from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.test import SimpleTestCase
from .templatetags.navegacion_sstt import enlace_pagina


class NavegacionCompartidaTests(SimpleTestCase):
    def render(self, pagina=2, **opciones):
        datos={"pagina":Paginator(range(120),50).get_page(pagina),
               "querystring":"servicios=A&servicios=B&contratista=Uno&contratista=Dos&q=cuenta"}
        datos.update(opciones)
        return render_to_string("revisiones/componentes/paginacion.html",datos)

    def enlaces(self, html):
        return [unescape(v) for v in re.findall(r'href="([^"]+)"',html)]

    def test_multiseleccion_conservada_y_pagina_sustituida(self):
        url=enlace_pagina("servicios=A&servicios=B&contratista=Uno&contratista=Dos&page=8&page=9",2)
        datos=parse_qs(urlsplit(url).query)
        self.assertEqual(datos["servicios"],["A","B"])
        self.assertEqual(datos["contratista"],["Uno","Dos"])
        self.assertEqual(datos["page"],["2"])

    def test_detalle_conserva_pagina_principal_y_ancla(self):
        url=enlace_pagina("page=4&cuenta=FIR-1&page_detalle=1",2,"page_detalle","historial-preventivos")
        datos=parse_qs(urlsplit(url).query)
        self.assertEqual(datos["page"],["4"])
        self.assertEqual(datos["page_detalle"],["2"])
        self.assertEqual(urlsplit(url).fragment,"historial-preventivos")

    def test_solo_enlaces_validos_en_primera_ultima_e_intermedia(self):
        for pagina, esperadas in ((1,["2"]),(2,["1","3"]),(3,["2"])):
            with self.subTest(pagina=pagina):
                numeros=[parse_qs(urlsplit(url).query)["page"][0] for url in self.enlaces(self.render(pagina))]
                self.assertEqual(numeros,esperadas)

    def test_parametros_vacios_no_se_pierden(self):
        datos=parse_qs(urlsplit(enlace_pagina("estado=&fecha_desde=&contratistas_filtrados=1",2)).query,
                       keep_blank_values=True)
        self.assertEqual(datos["estado"],[""])
        self.assertEqual(datos["fecha_desde"],[""])
        self.assertEqual(datos["contratistas_filtrados"],["1"])

    def test_una_pagina_se_oculta_salvo_variante_siempre(self):
        pagina=Paginator([],50).get_page(1)
        html=render_to_string("revisiones/componentes/paginacion.html",{"pagina":pagina})
        self.assertEqual(html.strip(),"")
        html=render_to_string("revisiones/componentes/paginacion.html",
            {"pagina":pagina,"siempre":True,"agrupada":True,"clase":"cuentas-paginacion"})
        self.assertIn("Página 1 de 1",html)
        self.assertIn('class="cuentas-paginacion"',html)
        self.assertEqual(self.enlaces(html),[])

    def test_variantes_conservan_clases_y_etiqueta_accesible(self):
        html=self.render(agrupada=True,clase_enlace="btn alt",etiqueta="Páginas de ODT")
        self.assertIn('class="pagination" role="navigation"',html)
        self.assertEqual(html.count('class="btn alt"'),2)
        self.assertIn('aria-label="Páginas de ODT"',html)
        historial=self.render(clase="hist-nav",clase_enlace="hist-tab")
        self.assertIn('<nav class="hist-nav"',historial)
        self.assertEqual(historial.count('class="hist-tab"'),2)

    def test_unicode_y_texto_hostil_viajan_como_datos_no_html(self):
        url=enlace_pagina('q=%22%3E%3Cscript%3E&contratista=Josu%C3%A9',2)
        self.assertEqual(parse_qs(urlsplit(url).query)["contratista"],["Josué"])
        html=self.render(querystring='q=%22%3E%3Cscript%3E')
        self.assertNotIn("<script>",html)
        self.assertEqual(parse_qs(urlsplit(self.enlaces(html)[0]).query)["q"],['"><script>'])

    def test_parametros_no_admitidos_y_paginas_no_positivas_fallan(self):
        with self.assertRaises(ValueError):
            enlace_pagina("",2,"otro_campo")
        for numero in (0,-1,"invalido"):
            with self.subTest(numero=numero), self.assertRaises(ValueError):
                enlace_pagina("",numero)

    def test_numeros_grandes_no_se_localizan_en_el_enlace(self):
        pagina=Paginator(range(100100),50).get_page(1000)
        html=render_to_string("revisiones/componentes/paginacion.html",{"pagina":pagina})
        numeros=[parse_qs(urlsplit(url).query)["page"][0] for url in self.enlaces(html)]
        self.assertEqual(numeros,["999","1001"])
