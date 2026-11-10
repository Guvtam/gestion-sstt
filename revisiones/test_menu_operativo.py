from io import StringIO
from types import SimpleNamespace

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.template import Context, Template
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase
from django.urls import resolve, reverse

from .navegacion import datos_menu


class MenuOperativoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("configurar_perfiles", stdout=StringIO())
        cls.admin = User.objects.create_superuser("admin", password="prueba")
        cls.coordinador = User.objects.create_user("coordinador_nuevo")
        cls.coordinador.groups.add(Group.objects.get(name="Coordinador"))
        cls.calendario = User.objects.create_user("consulta_visitas")
        cls.calendario.groups.add(Group.objects.get(name="Calendario de visitas"))

    def peticion(self, nombre, usuario=None, referente="", args=None):
        request = RequestFactory().get(reverse(nombre, args=args), HTTP_REFERER=referente)
        request.user = usuario or self.admin
        request.resolver_match = resolve(request.path)
        return request

    def test_mismo_orden_y_solo_una_opcion_activa_en_distintas_pantallas(self):
        orden = None
        for pantalla in ("bandeja", "analisis_odt", "estadisticas_correcciones", "contratistas:listado", "administrar_cuentas"):
            menu = datos_menu(self.peticion(pantalla), {})
            nombres = [o["nombre"] for o in menu["opciones"]]
            orden = orden or nombres
            self.assertEqual(nombres, orden)
            self.assertEqual([o["nombre"] for o in menu["opciones"] if o["activa"]], [pantalla])

    def test_coordinador_solo_bandeja_y_calendario(self):
        menu = datos_menu(self.peticion("bandeja", self.coordinador), {})
        self.assertEqual([o["nombre"] for o in menu["opciones"]], ["bandeja", "calendario_servicios"])

    def test_perfil_calendario_no_recibe_opciones_de_pagos(self):
        menu = datos_menu(self.peticion("calendario_servicios", self.calendario), {})
        self.assertEqual([o["nombre"] for o in menu["opciones"]], ["calendario_servicios"])
        self.assertEqual(menu["volver"], reverse("calendario_servicios"))

    def test_regreso_conserva_filtros_multiseleccion_y_pagina(self):
        anterior = "/?servicios=A&servicios=B&page=4&fecha_desde="
        menu = datos_menu(self.peticion("analisis_odt", referente="http://testserver"+anterior), {})
        self.assertEqual(menu["volver"], anterior)

    def test_no_acepta_destinos_externos_acciones_ni_rutas_no_autorizadas(self):
        for referente in ("https://otro.cl/", "//otro.cl/", "http://testserver/guardar-fila/", "http://testserver/admin/", "http://testserver/no-existe/"):
            menu = datos_menu(self.peticion("analisis_odt", referente=referente), {})
            self.assertEqual(menu["volver"], "/")
        menu = datos_menu(self.peticion("calendario_servicios", self.calendario, "http://testserver/"), {})
        self.assertEqual(menu["volver"], reverse("calendario_servicios"))

    def test_regreso_directo_a_facturacion_con_periodo_y_contratistas(self):
        request = self.peticion("detalle_facturacion", args=[3])
        menu = datos_menu(request, {"facturacion": SimpleNamespace(periodo_id=7)})
        self.assertEqual(menu["volver"], reverse("historial_facturacion")+"?periodo=7")
        self.assertTrue(next(o for o in menu["opciones"] if o["nombre"]=="historial_facturacion")["activa"])
        menu = datos_menu(self.peticion("contratistas:editar", args=[1]), {})
        self.assertEqual(menu["volver"], reverse("contratistas:listado"))

    def test_menu_componente_accesible_y_sin_html_del_referente(self):
        request = self.peticion("analisis_odt", referente='http://testserver/?q=%22%3E%3Cscript%3E')
        html = Template("{% load navegacion_sstt %}{% menu_sstt %}").render(Context({"request": request}))
        self.assertIn('aria-label="Menú principal SSTT"', html)
        self.assertIn('data-sstt-volver', html)
        self.assertEqual(html.count('aria-current="page"'), 1)
        self.assertNotIn('<script>', html)

    def test_tablas_resumen_y_detalle_tienen_barras_arriba_y_abajo(self):
        request = self.peticion("estadisticas_correcciones")
        html = render_to_string("revisiones/estadisticas_correcciones.html", {"request":request})
        self.assertEqual(html.count('data-tabla-desplazable'), 2)
        self.assertEqual(html.count('data-scroll-superior'), 2)
        self.assertEqual(html.count('data-scroll-tabla'), 2)
        self.assertEqual(html.count('tablas_desplazables.js'), 1)
        self.assertLess(html.index('data-sstt-menu'), html.index('<main'))

    def test_menu_unico_antes_del_contenido_y_estaticos_una_vez(self):
        request = self.peticion("bandeja")
        for plantilla in ("bandeja", "analisis_odt", "mantenimientos_preventivos", "calendario_servicios", "odt_modificadas", "administrar_cuentas"):
            html = render_to_string("revisiones/"+plantilla+".html", {"request":request, "bandeja_url":"bandeja", "filtros":{}})
            self.assertEqual(html.count('aria-label="Menú principal SSTT"'), 1, plantilla)
            self.assertEqual(html.count('navegacion.css'), 1, plantilla)
            self.assertEqual(html.count('navegacion.js'), 1, plantilla)
            self.assertLess(html.index('data-sstt-menu'), html.index('<main'), plantilla)
