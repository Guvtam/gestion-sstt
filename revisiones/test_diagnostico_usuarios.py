import json
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from .models import ODT, VinculoCoordinador


class DiagnosticoUsuariosTests(TestCase):
    def informe(self, **opciones):
        salida = StringIO()
        call_command("diagnosticar_usuarios", como_json=True, stdout=salida, **opciones)
        return json.loads(salida.getvalue())

    def permiso(self, codigo):
        return Permission.objects.get_or_create(
            content_type=ContentType.objects.get_for_model(ODT), codename=codigo,
            defaults={"name": codigo})[0]

    def test_staff_no_equivale_a_permisos_y_no_expone_datos_personales(self):
        User.objects.create_user("operador", password="secreto-de-prueba", email="privado@example.test", is_staff=True)
        info = self.informe()[0]
        self.assertTrue(info["staff"])
        self.assertFalse(info["perfil_coordinador"])
        self.assertEqual(info["permisos_django"], [])
        self.assertIn("Sin permiso para abrir la bandeja.", info["avisos"])
        self.assertNotIn("secreto-de-prueba", json.dumps(info))
        self.assertNotIn("privado@example.test", json.dumps(info))

    def test_permisos_directos_y_por_grupo_se_incluyen(self):
        usuario = User.objects.create_user("operador")
        grupo = Group.objects.create(name="Revisores")
        grupo.permissions.add(self.permiso("ver_bandeja_sstt"))
        usuario.groups.add(grupo)
        usuario.user_permissions.add(self.permiso("revisar_pago_sstt"))
        info = self.informe(usuario="operador")[0]
        self.assertEqual(info["grupos"], ["Revisores"])
        self.assertEqual(info["permisos_django"], ["revisiones.revisar_pago_sstt", "revisiones.ver_bandeja_sstt"])

    def test_vinculo_inactivo_y_permisos_adicionales_no_ocultan_restriccion(self):
        usuario = User.objects.create_user("login_coordinador")
        VinculoCoordinador.objects.create(usuario=usuario, usuario_softguard="rsilva", activo=False)
        usuario.user_permissions.add(self.permiso("exportar_pagos_sstt"))
        info = self.informe()[0]
        self.assertTrue(info["perfil_coordinador"])
        self.assertIsNone(info["responsable_softguard"])
        self.assertTrue(any("acceso operativo bloqueado" in aviso for aviso in info["avisos"]))
        self.assertTrue(any("sigue restringiendo" in aviso for aviso in info["avisos"]))

    def test_historico_y_superusuario_se_distinguen(self):
        User.objects.create_user("rsilva")
        User.objects.create_superuser("administrador", password="prueba")
        informes = {i["usuario"]: i for i in self.informe()}
        self.assertEqual(informes["rsilva"]["responsable_softguard"], "rsilva")
        self.assertFalse(informes["administrador"]["perfil_coordinador"])
        self.assertTrue(informes["administrador"]["superusuario"])

    def test_inactivo_y_usuario_ausente(self):
        User.objects.create_user("inactivo", is_active=False)
        self.assertIn("Usuario inactivo: no puede iniciar sesión.", self.informe()[0]["avisos"])
        with self.assertRaises(CommandError):
            self.informe(usuario="no_existe")

    def test_solo_select_sin_sesiones_ni_sql_server(self):
        User.objects.create_user("rsilva")
        with patch("revisiones.servicios_sql.obtener_conexion_sql") as conectar, CaptureQueriesContext(connection) as consultas:
            self.informe()
        conectar.assert_not_called()
        self.assertTrue(all(q["sql"].lstrip().upper().startswith("SELECT") for q in consultas))

    def test_texto_y_base_sin_usuarios(self):
        salida = StringIO()
        call_command("diagnosticar_usuarios", stdout=salida)
        self.assertIn("Usuarios revisados: 0", salida.getvalue())
        User.objects.create_user("sin_permisos")
        salida = StringIO()
        call_command("diagnosticar_usuarios", stdout=salida)
        self.assertIn("Usuario: sin_permisos", salida.getvalue())
        self.assertIn("Revisar: Sin permiso", salida.getvalue())
