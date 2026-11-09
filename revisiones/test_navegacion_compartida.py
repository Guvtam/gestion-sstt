from html import unescape
from urllib.parse import urlsplit, parse_qs
import re

from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.test import SimpleTestCase, RequestFactory
from django.contrib.auth.models import AnonymousUser
from .templatetags.navegacion_sstt import enlace_pagina


class NavegacionCompartidaTests(SimpleTestCase):
    def render(self, pagina=2, **opciones):
        datos={"pagina":pagina if hasattr(pagina, "paginator") else Paginator(range(120),50).get_page(pagina),
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

    def test_numerada_muestra_primera_todos_los_numeros_y_pagina_actual(self):
        pagina = Paginator(range(350), 50).get_page(4)
        html = self.render(pagina=pagina, numerada=True)
        self.assertIn("Primera página", html)
        self.assertIn('aria-current="page"', html)
        self.assertIn('aria-label="Página 4 actual"', html)
        for numero in (1, 2, 3, 5, 6, 7):
            self.assertIn(f'aria-label="Ir a página {numero}"', html)
        for url in self.enlaces(html):
            parametros = parse_qs(urlsplit(url).query)
            self.assertEqual(parametros["servicios"], ["A", "B"])
            self.assertEqual(parametros["contratista"], ["Uno", "Dos"])
            self.assertEqual(len(parametros["page"]), 1)

    def test_numerada_acota_listados_grandes_y_no_enlaza_paginas_invalidas(self):
        from .templatetags.navegacion_sstt import paginas_numeradas
        for actual in (1, 500, 1000):
            pagina = Paginator(range(50000), 50).get_page(actual)
            numeros = paginas_numeradas(pagina)
            self.assertLessEqual(len(numeros), 9)
            self.assertIn(actual, numeros)
            html = self.render(pagina=pagina, numerada=True)
            destinos = [int(parse_qs(urlsplit(url).query)["page"][0]) for url in self.enlaces(html)]
            self.assertTrue(all(1 <= numero <= 1000 for numero in destinos))
        html = self.render(pagina=Paginator(range(350),50).get_page(1), numerada=True)
        self.assertIn('aria-disabled="true">Primera página', html)

    def test_bandeja_navegacion_arriba_y_abajo_conserva_multiseleccion(self):
        from django.test import override_settings
        pagina = Paginator(range(350), 50).get_page(3)
        request = RequestFactory().get("/")
        request.user = AnonymousUser()
        # Renderiza la estructura sin consultar ODT ni resolver coordinadores.
        with override_settings(ROOT_URLCONF="config.urls"):
            html = render_to_string("revisiones/bandeja.html", {
                "pagina": pagina, "querystring": "servicios=A&servicios=B&contratista=Uno&contratista=Dos",
                "registros": [], "filtros": {}, "bandeja_url":"bandeja", "request":request,
            })
        self.assertIn('aria-label="Paginación superior de ODT"', html)
        self.assertIn('aria-label="Paginación inferior de ODT"', html)
        self.assertEqual(html.count('aria-current="page"'), 2)
        self.assertLess(html.index('aria-label="Paginación superior de ODT"'), html.index('id="tablaScrollSuperior"'))
        self.assertGreater(html.index('aria-label="Paginación inferior de ODT"'), html.index('</table>'))

    def test_estilos_historial_compartidos_en_pantallas_operativas(self):
        for plantilla in ("bandeja", "analisis_odt", "detalle_facturacion"):
            with self.subTest(plantilla=plantilla):
                # Solo verificamos la carga única del estilo común del layout.
                if plantilla == "detalle_facturacion":
                    from types import SimpleNamespace
                    datos = {"facturacion": SimpleNamespace(periodo_id=1), "items": []}
                else:
                    datos = {"registros": [], "filtros": {}, "bandeja_url":"bandeja", "vista": "todas"}
                request = RequestFactory().get("/")
                request.user = AnonymousUser()
                datos["request"] = request
                html = render_to_string(f"revisiones/{plantilla}.html", datos)
                self.assertEqual(html.count("historial_modal.css"), 1)
