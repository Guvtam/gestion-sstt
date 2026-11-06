from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import AnonymousUser, Permission, User
from django.core.exceptions import PermissionDenied
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory, TestCase
from django.urls import reverse

from .acceso_coordinadores import datos_coordinador, es_coordinador_sstt, coordinador_visible
from .admin import VinculoCoordinadorForm
from .casos_uso.autorizacion import exigir_permiso_operativo
from .coordinadores_softguard import COORDINADORES_SOFTGUARD
from .models import VinculoCoordinador


class VinculosCoordinadoresTests(TestCase):
    def setUp(self):
        self.responsables = list(COORDINADORES_SOFTGUARD.values())
        self.usuario = User.objects.create_user("nuevo_login", password="prueba")
        self.responsable = self.responsables[0]
        self.vinculo = VinculoCoordinador.objects.create(
            usuario=self.usuario, usuario_softguard=self.responsable["usuario"])

    def recargar_usuario(self):
        return User.objects.get(pk=self.usuario.pk)

    def test_login_distinto_resuelve_identidad_estable(self):
        self.assertEqual(datos_coordinador(self.usuario), self.responsable)
        self.assertTrue(es_coordinador_sstt(self.usuario))

    def test_cambiar_nombre_login_conserva_vinculo(self):
        User.objects.filter(pk=self.usuario.pk).update(username="otro_login")
        self.assertEqual(datos_coordinador(self.recargar_usuario()), self.responsable)

    def test_vinculo_inactivo_sigue_restringido_sin_datos(self):
        self.vinculo.activo = False
        self.vinculo.save()
        usuario = self.recargar_usuario()
        self.assertTrue(es_coordinador_sstt(usuario))
        self.assertIsNone(datos_coordinador(usuario))

    def test_desactivar_no_reactiva_fallback_por_nombre(self):
        User.objects.filter(pk=self.usuario.pk).update(username=self.responsable["usuario"])
        self.vinculo.activo = False
        self.vinculo.save()
        self.assertIsNone(datos_coordinador(self.recargar_usuario()))

    def test_compatibilidad_usuario_historico_sin_vinculo(self):
        historico = User.objects.create_user(self.responsables[1]["usuario"])
        self.assertEqual(datos_coordinador(historico), self.responsables[1])
        self.assertTrue(es_coordinador_sstt(historico))

    def test_dato_desconocido_falla_cerrado(self):
        self.vinculo.usuario_softguard = "desconocido"
        self.vinculo.save()
        usuario = self.recargar_usuario()
        self.assertTrue(es_coordinador_sstt(usuario))
        self.assertIsNone(datos_coordinador(usuario))

    def test_excepciones_admin_se_conservan(self):
        for nombre in ("admin", "jiturriaga"):
            usuario = User.objects.create_user(nombre)
            self.assertFalse(es_coordinador_sstt(usuario))

    def test_anonimo_sin_consultas(self):
        with self.assertNumQueries(0):
            self.assertIsNone(datos_coordinador(AnonymousUser()))
            self.assertFalse(es_coordinador_sstt(AnonymousUser()))

    def test_consulta_reutilizada_solo_en_instancia_de_usuario(self):
        usuario = self.recargar_usuario()
        with self.assertNumQueries(1):
            for _ in range(4):
                self.assertEqual(datos_coordinador(usuario), self.responsable)
                self.assertTrue(es_coordinador_sstt(usuario))
        VinculoCoordinador.objects.filter(pk=self.vinculo.pk).update(activo=False)
        self.assertIsNone(datos_coordinador(self.recargar_usuario()))

    def test_no_adquiere_operaciones_financieras(self):
        permiso, _ = Permission.objects.get_or_create(
            codename="exportar_pagos_sstt", content_type=ContentType.objects.get(app_label="revisiones", model="odt"),
            defaults={"name":"Exportar pagos"})
        self.usuario.user_permissions.add(permiso)
        with self.assertRaises(PermissionDenied):
            exigir_permiso_operativo(self.recargar_usuario(), "revisiones.exportar_pagos_sstt")

    def test_coordinador_ve_solo_su_responsable(self):
        request = RequestFactory().get("/")
        request.user = self.usuario
        with patch("revisiones.acceso_coordinadores.identificar_coordinadores_odt",
                   return_value={1: dict(self.responsable, identificado=True)}):
            self.assertTrue(coordinador_visible(request, 1))
        request = RequestFactory().get("/")
        request.user = self.recargar_usuario()
        with patch("revisiones.acceso_coordinadores.identificar_coordinadores_odt",
                   return_value={1: dict(self.responsables[1], identificado=True)}):
            self.assertFalse(coordinador_visible(request, 1))

    def test_vinculo_inactivo_bloquea_bandeja(self):
        self.vinculo.activo = False
        self.vinculo.save()
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.get(reverse("bandeja")).status_code, 403)

    def test_formulario_no_acepta_identidades_desconocidas(self):
        form = VinculoCoordinadorForm(data={"usuario":self.usuario.pk,
            "usuario_softguard":"inventado", "activo":True}, instance=self.vinculo)
        self.assertFalse(form.is_valid())
        self.assertIn("usuario_softguard", form.errors)

    def test_formulario_rechaza_cuentas_administrativas(self):
        usuario = User.objects.create_superuser("operador_admin", password="prueba")
        form = VinculoCoordinadorForm(data={"usuario":usuario.pk,
            "usuario_softguard":self.responsable["usuario"], "activo":True}, instance=self.vinculo)
        self.assertFalse(form.is_valid())

    def test_formulario_evitar_doble_acceso_legacy(self):
        historico = User.objects.create_user(self.responsable["usuario"])
        datos = {"usuario":self.usuario.pk, "usuario_softguard":self.responsable["usuario"], "activo":True}
        self.assertFalse(VinculoCoordinadorForm(data=datos, instance=self.vinculo).is_valid())
        historico.is_active = False
        historico.save()
        self.assertTrue(VinculoCoordinadorForm(data=datos, instance=self.vinculo).is_valid())

    def test_admin_requiere_permisos_y_no_permite_borrado(self):
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.get(reverse("admin:revisiones_vinculocoordinador_changelist")).status_code, 302)
        administrador = admin.site._registry[VinculoCoordinador]
        self.assertFalse(administrador.has_delete_permission(RequestFactory().get("/"), self.vinculo))
