from datetime import date
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import ODT, VinculoCoordinador


class UsuariosCalendarioTests(TestCase):
    def setUp(self):
        call_command("configurar_perfiles", stdout=StringIO())
        self.odt = ODT.objects.create(numero=101, cuenta_completa="FIR-101 - Cuenta protegida",
            contratista="Proveedor privado", tecnico="Técnico", servicio="MANTENIMIENTO PREVENTIVO",
            valor_pago_tecnico=987654, fecha_visita=date(2026,11,10), estado_softguard="Asignado")

    def usuario(self, nombre, grupo):
        usuario = User.objects.create_user(nombre, password="prueba")
        usuario.groups.add(Group.objects.get(name=grupo))
        self.client.force_login(usuario)
        return usuario

    def test_coordinador_sin_identidad_entra_a_vistas_vacias_sin_consultar_sql(self):
        self.usuario("coordinador_nuevo", "Coordinador")
        with patch("revisiones.acceso_coordinadores.identificar_coordinadores_odt", side_effect=AssertionError("No consultar origen sin identidad")):
            respuesta = self.client.get(reverse("bandeja"), {"estado":"", "fecha_desde":"", "fecha_hasta":""})
            calendario = self.client.get(reverse("calendario_servicios"), {"mes":"2026-11"})
            servicios = self.client.get(reverse("calendario_servicios"), {"mes":"2026-11", "formato":"servicios"})
            contratistas = self.client.get(reverse("contratistas_disponibles_ajax"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "no tiene un responsable activo vinculado")
        self.assertNotContains(respuesta, "Cuenta protegida")
        self.assertEqual(respuesta.context["pagina"].paginator.count, 0)
        self.assertEqual(calendario.status_code, 200)
        self.assertEqual(calendario.context["cantidad"], 0)
        self.assertEqual(calendario.context["disponibles_mes"], 0)
        self.assertNotContains(calendario, "Cuenta protegida")
        self.assertEqual(servicios.json(), {"servicios":[]})
        self.assertEqual(contratistas.json(), {"contratistas":[]})

    def test_vinculo_inactivo_o_desconocido_no_muestra_odt_y_no_permite_operaciones(self):
        usuario = self.usuario("coordinador_nuevo", "Coordinador")
        vinculo = VinculoCoordinador.objects.create(usuario=usuario, usuario_softguard="rsilva", activo=False)
        for activo, responsable in ((False,"rsilva"),(True,"no_existe")):
            vinculo.activo, vinculo.usuario_softguard = activo, responsable
            vinculo.save()
            respuesta = self.client.get(reverse("bandeja"))
            self.assertEqual(respuesta.status_code, 200)
            self.assertEqual(respuesta.context["pagina"].paginator.count, 0)
            with patch("revisiones.vistas.odt.consultar_historial_odt") as sql:
                self.assertEqual(self.client.get(reverse("historial_odt", args=[101])).status_code, 403)
                self.assertEqual(self.client.post(reverse("actualizar_informe"), {"numero":101,"estado":"ENVIADO"}).status_code,403)
                self.assertEqual(self.client.post(reverse("cambiar_estado_correccion"), {"numero":101,"estado":"EN_PROCESO"}).status_code,403)
            sql.assert_not_called()
        self.odt.refresh_from_db()
        self.assertEqual(self.odt.estado_informe, "NO_ENVIADO")

    def test_perfil_calendario_solo_consulta_y_redireccion_despues_del_login(self):
        usuario = self.usuario("consulta_visitas", "Calendario de visitas")
        self.assertFalse(usuario.is_staff)
        self.assertFalse(usuario.has_perm("revisiones.ver_bandeja_sstt"))
        self.assertTrue(usuario.has_perm("revisiones.ver_calendario_sstt"))
        self.assertRedirects(self.client.get(reverse("bandeja")), reverse("calendario_servicios"), fetch_redirect_response=False)
        respuesta = self.client.get(reverse("calendario_servicios"), {"mes":"2026-11"})
        self.assertContains(respuesta, "Cuenta protegida")
        self.assertNotContains(respuesta, "987654")
        self.assertNotContains(respuesta, "Monto")
        self.assertNotContains(respuesta, "numero_odt=")
        self.assertNotContains(respuesta, reverse("mantenimientos_preventivos"))
        self.assertContains(respuesta, "Cerrar sesión")
        self.assertEqual(self.client.get(reverse("bandeja_creacion")).status_code,403)
        self.assertEqual(self.client.post(reverse("guardar_fila"), {"numero":101,"monto":"0"}).status_code,403)
        self.assertEqual(self.client.get(reverse("historial_odt",args=[101])).status_code,403)
        self.assertEqual(self.client.get(reverse("historial_facturacion")).status_code,403)

    def test_grupo_calendario_idempotente_y_no_cambia_usuarios(self):
        usuario = self.usuario("consulta_visitas", "Calendario de visitas")
        call_command("configurar_perfiles", stdout=StringIO())
        grupo = Group.objects.get(name="Calendario de visitas")
        self.assertEqual(list(grupo.permissions.values_list("codename", flat=True)), ["ver_calendario_sstt"])
        self.assertEqual(User.objects.count(),1)
        usuario.refresh_from_db()
        self.assertFalse(usuario.is_staff)
        self.assertFalse(usuario.is_superuser)

    def test_usuario_sin_permisos_sigue_denegado(self):
        usuario = User.objects.create_user("sin_permisos")
        self.client.force_login(usuario)
        self.assertEqual(self.client.get(reverse("calendario_servicios")).status_code,403)
