from unittest.mock import patch

from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from .models import ODT


class PermisosContratistasAjaxTests(TestCase):
    def setUp(self):
        self.url = reverse("contratistas_disponibles_ajax")
        self.user = User.objects.create_user("usuario_lectura")
        ODT.objects.create(numero=900, contratista="Contratista de prueba")

    def test_anonimo_requiere_sesion(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_sesion_sin_permiso_no_expone_contratistas(self):
        self.client.force_login(self.user)
        with patch("revisiones.vistas.bandeja.opciones_contratistas") as consulta:
            self.assertEqual(self.client.get(self.url).status_code, 403)
        consulta.assert_not_called()

    def test_permiso_bandeja_permite_consulta(self):
        ct = ContentType.objects.get_for_model(ODT)
        permiso, _ = Permission.objects.get_or_create(
            content_type=ct, codename="ver_bandeja_sstt",
            defaults={"name": "Ver bandeja SSTT"},
        )
        self.user.user_permissions.add(permiso)
        self.client.force_login(self.user)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["contratistas"], ["Contratista de prueba"])
