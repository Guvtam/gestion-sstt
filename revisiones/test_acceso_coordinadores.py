from types import SimpleNamespace
from unittest.mock import patch
from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.template import engines
from django.test import RequestFactory, TestCase
from .models import ODT
from . import views
from .acceso_coordinadores import AccesoCoordinadorMiddleware, es_coordinador_sstt


class AccesoCoordinadoresTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user("rsilva")
        group = Group.objects.create(name="Coordinador")
        self.user.groups.add(group)
        ct = ContentType.objects.get_for_model(ODT)
        for code in ("ver_bandeja_sstt", "ver_historial_sstt", "cambiar_informe_sstt"):
            perm, _ = Permission.objects.get_or_create(content_type=ct, codename=code)
            group.permissions.add(perm)
        for n in (1, 2, 3):
            ODT.objects.create(numero=n, contratista=str(n))

    def request(self, route="bandeja", method="get", data=None):
        req = getattr(self.factory, method)("/", data or {})
        req.user = User.objects.get(pk=self.user.pk)
        req.resolver_match = SimpleNamespace(url_name=route)
        return req

    @staticmethod
    def info(numero):
        return {"identificado": numero != 3, "usuario": {1: "rsilva", 2: "jtapia"}.get(numero),
                "nombre": "Coordinador"}

    def middleware(self, req, kwargs=None):
        return AccesoCoordinadorMiddleware(lambda r: HttpResponse()).process_view(
            req, lambda r: HttpResponse(), (), kwargs or {})

    def test_ambos_nombres_de_grupo(self):
        self.assertTrue(es_coordinador_sstt(self.user))
        self.user.groups.clear()
        self.user.groups.add(Group.objects.create(name="Coordinadores SSTT"))
        self.assertTrue(es_coordinador_sstt(self.user))

    def test_bandeja_solo_propias_aunque_se_manipule_el_filtro(self):
        for parametro in ("", "jtapia", "SIN_IDENTIFICAR"):
            req = self.request(data={"coordinador": parametro, "estado": "",
                                     "fecha_desde": "", "fecha_hasta": ""})
            with patch("revisiones.acceso_coordinadores.identificar_coordinador_odt", side_effect=self.info), \
                 patch("revisiones.views.identificar_coordinador_odt", side_effect=self.info), \
                 patch("revisiones.views.render", side_effect=lambda r, t, c: c):
                context = views.bandeja(req)
            self.assertEqual({o.numero for o in context["registros"]}, {1})
            self.assertEqual(context["filtros"]["coordinador"], "rsilva")
            self.assertTrue(context["es_coordinador"])

    def test_otras_paginas_redirigen(self):
        for route in ("odt_modificadas", "historial_facturacion", "detalle", "index"):
            self.assertEqual(self.middleware(self.request(route)).status_code, 302)

    def test_operaciones_ajenas_bloqueadas(self):
        with self.assertRaises(PermissionDenied):
            self.middleware(self.request("guardar_fila", "post"))

    def test_historial_informe_y_correccion_excluyen_sin_identificar(self):
        with patch("revisiones.acceso_coordinadores.identificar_coordinador_odt", side_effect=self.info):
            for n in (1,):
                self.assertIsNone(self.middleware(self.request("historial_odt"), {"numero": n}))
            with self.assertRaises(PermissionDenied):
                self.middleware(self.request("historial_odt"), {"numero": 2})
            for n in ("2", "3"):
                with self.assertRaises(PermissionDenied):
                    self.middleware(self.request("historial_odt"), {"numero": int(n)})
                for route in ("actualizar_informe", "cambiar_estado_correccion"):
                    with self.assertRaises(PermissionDenied):
                        self.middleware(self.request(route, "post", {"numero": n}))

    def test_fallo_sql_no_da_acceso(self):
        with patch("revisiones.acceso_coordinadores.identificar_coordinador_odt", side_effect=RuntimeError):
            self.assertEqual(self.middleware(self.request("historial_odt"), {"numero": 1}).status_code, 503)

    def test_usuario_sin_vinculo_denegado(self):
        self.user.username = "desconocido"
        self.user.save()
        with self.assertRaises(PermissionDenied):
            self.middleware(self.request())

    def test_superusuario_sin_restriccion(self):
        self.user.is_superuser = True
        self.user.save()
        self.assertIsNone(self.middleware(self.request("historial_facturacion")))

    def test_ajax_solo_contratistas_visibles(self):
        with patch("revisiones.acceso_coordinadores.identificar_coordinador_odt", side_effect=self.info):
            response = views.contratistas_disponibles_ajax(self.request("contratistas_disponibles_ajax"))
        import json
        self.assertEqual(set(json.loads(response.content)["contratistas"]), {"1"})

    def test_plantilla_compila(self):
        engines["django"].get_template("revisiones/bandeja.html")


    def test_enlace_odt_exacto_respeta_alcance_del_usuario(self):
        for numero, expected in (("1", {1}), ("2", set()), ("3", set()), ("invalido", set())):
            req = self.request(data={"numero_odt": numero, "estado": "",
                                     "fecha_desde": "", "fecha_hasta": ""})
            with patch("revisiones.acceso_coordinadores.identificar_coordinador_odt", side_effect=self.info), \
                 patch("revisiones.views.identificar_coordinador_odt", side_effect=self.info), \
                 patch("revisiones.views.render", side_effect=lambda r, t, c: c):
                context = views.bandeja(req)
            self.assertEqual({o.numero for o in context["registros"]}, expected)


class EstadoModificacionTests(TestCase):
    def setUp(self):
        from decimal import Decimal
        from .models import CorreccionODT
        self.factory = RequestFactory()
        self.user = User.objects.create_user("rsilva")
        self.odt = ODT.objects.create(numero=10, servicio="A", servicio_editado="B",
                                     valor_pago_tecnico=Decimal("100"), valor_pago_editado=Decimal("200"))
        with __import__("django.db", fromlist=["transaction"]).transaction.atomic():
            from .correcciones import registrar_cambio_manual
            self.seguimiento = registrar_cambio_manual(self.odt, self.user)

    def enviar(self, estado="EN_PROCESO"):
        req = self.factory.post("/", {"numero": "10", "estado": estado})
        req.user = self.user
        with patch("revisiones.views.coordinador_visible", return_value=True):
            return views.cambiar_estado_correccion(req)

    def test_procesada_y_actualizada_solo_al_coincidir_ambos_campos(self):
        from .correcciones import verificar_sincronizacion
        from django.db import transaction
        self.assertEqual(self.seguimiento.estado, "PENDIENTE")
        self.assertEqual(self.enviar().status_code, 200)
        self.seguimiento.refresh_from_db()
        self.assertEqual(self.seguimiento.estado, "EN_PROCESO")
        self.odt.servicio = "B"
        self.odt.save()
        with transaction.atomic():
            verificar_sincronizacion(self.odt)
        self.seguimiento.refresh_from_db()
        self.assertEqual(self.seguimiento.estado, "EN_PROCESO")
        self.odt.valor_pago_tecnico = 200
        self.odt.save()
        with transaction.atomic():
            verificar_sincronizacion(self.odt)
        self.seguimiento.refresh_from_db()
        self.assertEqual(self.seguimiento.estado, "ACTUALIZADA")

    def test_coordinador_no_puede_actualizar_manualmente(self):
        self.assertEqual(self.enviar("ACTUALIZADA").status_code, 400)

    def test_otro_coordinador_denegado(self):
        req = self.factory.post("/", {"numero": "10", "estado": "EN_PROCESO"})
        req.user = self.user
        with patch("revisiones.views.coordinador_visible", return_value=False):
            with self.assertRaises(PermissionDenied):
                views.cambiar_estado_correccion(req)

    def test_sin_modificaciones_no_se_puede_procesar(self):
        self.seguimiento.delete()
        self.odt.servicio_editado = None
        self.odt.valor_pago_editado = None
        self.odt.save()
        self.assertEqual(self.enviar().status_code, 409)

    def test_columna_revision_oculta_y_estado_visible(self):
        template = engines["django"].get_template("revisiones/bandeja.html")
        self.odt.estado_modificacion = "PENDIENTE"
        self.odt.puede_procesar_modificacion = True
        for coordinador in (True, False):
            with patch("django.urls.reverse", return_value="/test/"):
                html = template.render({"es_coordinador": coordinador, "registros": [self.odt],
                                        "filtros": {}, "request": SimpleNamespace(user=self.user)})
            self.assertIn("Estado de modificación", html)
            self.assertIn("modification-select", html)
            self.assertNotIn("Marcar procesada", html)
            self.assertIn(">Procesado</option>", html)
            self.assertEqual('<th hidden>Revisión</th>' in html, coordinador)


class AsignacionCoordinadorTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.odt = ODT.objects.create(numero=77)
        self.admin = User.objects.create_user("admin")
        self.juan = User.objects.create_user("jiturriaga")
        self.otro = User.objects.create_superuser("otro", password="test")

    def asignar(self, user, usuario="rsilva"):
        request = self.factory.post("/", {"numero": "77", "coordinador": usuario})
        request.user = user
        return views.asignar_coordinador(request)

    def test_admin_y_juan_autorizados(self):
        from .models import AsignacionCoordinadorODT
        for user in (self.admin, self.juan):
            with patch("revisiones.views.identificar_coordinador_softguard", return_value={"identificado": False}):
                self.assertEqual(self.asignar(user).status_code, 200)
            asignacion = AsignacionCoordinadorODT.objects.get(odt=self.odt)
            self.assertEqual(asignacion.usuario_coordinador, "rsilva")
            self.assertEqual(asignacion.asignado_por, user)
            asignacion.delete()

    def test_otros_usuarios_incluso_superusuario_denegados(self):
        with self.assertRaises(PermissionDenied):
            self.asignar(self.otro)

    def test_identificada_y_fallo_sql_no_permiten_asignar(self):
        from .models import AsignacionCoordinadorODT
        with patch("revisiones.views.identificar_coordinador_softguard", return_value={"identificado": True}):
            self.assertEqual(self.asignar(self.admin).status_code, 409)
        with patch("revisiones.views.identificar_coordinador_softguard", side_effect=RuntimeError):
            self.assertEqual(self.asignar(self.admin).status_code, 503)
        self.assertFalse(AsignacionCoordinadorODT.objects.exists())

    def test_asignacion_persistente_filtra_por_usuario_y_no_se_reasigna(self):
        from .coordinadores_softguard import identificar_coordinador_odt
        from .acceso_coordinadores import limitar_odts_coordinador
        with patch("revisiones.views.identificar_coordinador_softguard", return_value={"identificado": False}):
            self.assertEqual(self.asignar(self.juan).status_code, 200)
            self.assertEqual(self.asignar(self.admin, "jtapia").status_code, 409)
        self.assertEqual(identificar_coordinador_odt(77)["usuario"], "rsilva")
        for usuario, expected in (("rsilva", 1), ("jtapia", 0)):
            user = User.objects.create_user(usuario)
            req = self.factory.get("/")
            req.user = user
            self.assertEqual(limitar_odts_coordinador(req, ODT.objects.all()).count(), expected)

    def test_coordinador_invalido(self):
        self.assertEqual(self.asignar(self.admin, "inventado").status_code, 400)

    def test_selector_solo_procesado_como_opcion_manual(self):
        from html.parser import HTMLParser
        class Opciones(HTMLParser):
            def __init__(self):
                super().__init__()
                self.en_selector = False
                self.opciones = []
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == "select":
                    self.en_selector = "modification-select" in attrs.get("class", "")
                if tag == "option" and self.en_selector and "hidden" not in attrs:
                    self.opciones.append(attrs["value"])
            def handle_endtag(self, tag):
                if tag == "select":
                    self.en_selector = False
        template = engines["django"].get_template("revisiones/bandeja.html")
        for estado in ("", "PENDIENTE", "EN_PROCESO", "ACTUALIZADA"):
            self.odt.estado_modificacion = estado
            self.odt.puede_procesar_modificacion = estado == "PENDIENTE"
            with patch("django.urls.reverse", return_value="/test/"):
                html = template.render({"registros": [self.odt], "filtros": {},
                                        "es_coordinador": True, "request": SimpleNamespace(user=self.juan)})
            parser = Opciones()
            parser.feed(html)
            self.assertEqual(parser.opciones, ["EN_PROCESO"])
