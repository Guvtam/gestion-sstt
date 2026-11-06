import json
from datetime import datetime
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.template import engines
from django.test import TestCase, RequestFactory
from django.utils import timezone
from .models import ODT
from . import views

class BandejaCreacionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("admin", password="test")
        self.factory = RequestFactory()
        for numero, creacion, finalizacion, nombre in (
            (1, datetime(2026,10,25), datetime(2026,11,25), "Por creación"),
            (2, datetime(2026,9,25), datetime(2026,10,25), "Por finalización"),
        ):
            ODT.objects.create(numero=numero, fecha_creacion=timezone.make_aware(creacion),
                fecha_finalizacion=timezone.make_aware(finalizacion), contratista=nombre,
                servicio=views.SERVICIOS_PRINCIPALES[0], estado_softguard="Finalizado", valor_pago_tecnico=100)

    def request(self, **extra):
        request = self.factory.get("/", {"fecha_desde":"2026-10-21", "fecha_hasta":"2026-10-31",
                                        "estado":"Finalizado", **extra})
        request.user = self.user
        return request

    def contexto(self, creacion):
        with patch("revisiones.views.render", side_effect=lambda r,t,c:c), \
             patch("revisiones.views.identificar_coordinador_odt", return_value={"identificado":False}):
            return (views.bandeja_creacion if creacion else views.bandeja)(self.request())

    def test_fecha_correcta_en_filas_tarjetas_y_contratistas(self):
        for creacion, numero, contratista in ((True,1,"Por creación"),(False,2,"Por finalización")):
            c = self.contexto(creacion)
            self.assertEqual([o.numero for o in c["registros"]], [numero])
            self.assertEqual(c["total"]["cantidad"], 1)
            self.assertEqual(c["contratistas_seleccionados"], [contratista])
            self.assertEqual(c["bandeja_url"], "bandeja_creacion" if creacion else "bandeja")

    def test_ajax_respeta_fecha_creacion_y_mantiene_finalizacion_por_defecto(self):
        for extra, esperado in (({"campo_fecha":"creacion"}, "Por creación"),({}, "Por finalización")):
            r = views.contratistas_disponibles_ajax(self.request(**extra))
            self.assertEqual(json.loads(r.content)["contratistas"], [esperado])

    def test_tarjetas_boton_y_formulario_en_ambas_paginas(self):
        for creacion in (True,False):
            c = self.contexto(creacion)
            c["request"] = self.request()
            c["perms"] = {"revisiones": {"ver_bandeja_sstt":True, "exportar_pagos_sstt":True}}
            with patch("django.urls.reverse", side_effect=lambda nombre,*a,**k:"/"+str(nombre)+"/"):
                html = engines["django"].get_template("revisiones/bandeja.html").render(c)
            self.assertEqual('class="kpis kpis-operativos"' in html, not creacion)
            self.assertEqual('id="formFacturarPeriodo"' in html, not creacion)
            self.assertIn("Creación desde" if creacion else "Finalización desde", html)
            self.assertIn('action="/'+c["bandeja_url"]+'/"', html)
            if not creacion:
                self.assertLess(html.index("ODT por creación"),html.index("Mantenimientos preventivos"))

    def test_acceso_requiere_permiso(self):
        from django.core.exceptions import PermissionDenied
        self.user = get_user_model().objects.create_user("sin_permiso")
        with self.assertRaises(PermissionDenied):
            views.bandeja_creacion(self.request())

    def test_cuentas_sin_tecnico_se_incluyen_y_pueden_filtrarse(self):
        ODT.objects.create(numero=3, contratista="", tecnico="", servicio="MARCHA BLANCA",
            estado_softguard="Pendiente", fecha_creacion=timezone.make_aware(datetime(2026,10,25)))
        request = self.request(estado="")
        with patch("revisiones.views.render", side_effect=lambda r,t,c:c), \
             patch("revisiones.views.identificar_coordinador_odt", return_value={"identificado":False}):
            c = views.bandeja_creacion(request)
        self.assertEqual({o.numero for o in c["registros"]}, {1,3})
        self.assertIn(views.SIN_TECNICO_FILTRO,c["contratistas_seleccionados"])
        request = self.request(estado="", contratista=[views.SIN_TECNICO_FILTRO], contratistas_filtrados="1")
        with patch("revisiones.views.render", side_effect=lambda r,t,c:c), \
             patch("revisiones.views.identificar_coordinador_odt", return_value={"identificado":False}):
            c = views.bandeja_creacion(request)
        self.assertEqual([o.numero for o in c["registros"]],[3])
        ajax = views.contratistas_disponibles_ajax(self.request(estado="",campo_fecha="creacion"))
        self.assertIn(views.SIN_TECNICO_FILTRO,json.loads(ajax.content)["contratistas"])

    def test_creacion_predetermina_todos_estados_y_servicios(self):
        from unittest.mock import patch
        request = self.factory.get("/")
        request.user = self.user
        with patch("revisiones.views.render", side_effect=lambda r,t,c:c), \
             patch("revisiones.views.identificar_coordinador_odt", return_value={"identificado":False}):
            c = views.bandeja_creacion(request)
        self.assertEqual(c["filtros"]["estado"],"")
        self.assertEqual(c["servicios_seleccionados"],[])

    def test_deseleccionar_todo_sigue_sin_mostrar_filas(self):
        with patch("revisiones.views.render", side_effect=lambda r,t,c:c):
            c = views.bandeja_creacion(self.request(contratistas_filtrados="1"))
        self.assertEqual(list(c["registros"]),[])
