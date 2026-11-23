from datetime import date
from io import StringIO
from django.contrib.auth.models import User, Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse
from .models import ODT
from .acceso_calendario import GRUPO_INTERNOS

class CalendarioInternosTests(TestCase):
    def setUp(self):
        call_command("configurar_perfiles", stdout=StringIO())
        self.usuario=User.objects.create_user("consulta_interna",password="prueba")
        for n,t,s in ((1,"T. INTERNO - ServicioStgo","Santiago"),
                      (2,"T. INTERNO - ServicioViña","Viña"),
                      (3,"T. EXTERNO - Técnico de prueba","Externo secreto"),
                      (4,"","Sin técnico secreto"),
                      (5,"T. INTERNO - ServicioStgo adicional","Otro secreto")):
            ODT.objects.create(numero=n,tecnico=t,contratista="T. INTERNO - ServicioStgo",
                cuenta_completa=f"Cuenta {n}",servicio=s,fecha_visita=date(2026,11,10),estado_softguard="Finalizado")
        self.url=reverse("calendario_servicios")

    def habilitar(self):
        call_command("habilitar_calendario_internos",usuario=self.usuario.username,stdout=StringIO())
        self.client.force_login(self.usuario)

    def test_eventos_contadores_y_servicios_restringidos(self):
        self.habilitar()
        r=self.client.get(self.url,{"mes":"2026-11"})
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.context["cantidad"],2)
        self.assertEqual(r.context["disponibles_mes"],2)
        self.assertEqual(r.context["totales"]["realizadas"],2)
        for n in (3,4,5):self.assertNotContains(r,f"Cuenta {n}")
        s=self.client.get(self.url,{"mes":"2026-11","formato":"servicios"})
        self.assertEqual(set(s.json()["servicios"]),{"Santiago","Viña"})

    def test_parametros_no_amplian_alcance(self):
        self.habilitar()
        for p in ({"q":"Externo"},{"servicios":"Externo secreto","servicios_filtrados":"1"},{"q":"Cuenta 3"}):
            self.assertEqual(self.client.get(self.url,{"mes":"2026-11",**p}).context["cantidad"],0)

    def test_solo_consulta(self):
        self.habilitar()
        self.assertRedirects(self.client.get(reverse("bandeja")),self.url,fetch_redirect_response=False)
        for n in ("bandeja_creacion","historial_facturacion"):
            self.assertEqual(self.client.get(reverse(n)).status_code,403)
        self.assertEqual(self.client.get(reverse("historial_odt",args=[1])).status_code,403)
        for n,p in (("guardar_fila",{"numero":1,"monto":"2"}),
                    ("actualizar_informe",{"numero":1,"estado":"ENVIADO"})):
            self.assertEqual(self.client.post(reverse(n),p).status_code,403)

    def test_otro_usuario_conserva_calendario_completo(self):
        otro=User.objects.create_user("consulta_general")
        otro.groups.add(Group.objects.get(name="Calendario de visitas"))
        self.client.force_login(otro)
        self.assertEqual(self.client.get(self.url,{"mes":"2026-11"}).context["cantidad"],5)

    def test_idempotencia_y_reconfiguracion(self):
        self.habilitar();self.habilitar()
        call_command("configurar_perfiles",stdout=StringIO())
        self.assertEqual(self.usuario.groups.filter(name=GRUPO_INTERNOS).count(),1)
        self.assertEqual(set(self.usuario.get_all_permissions()),{"revisiones.ver_calendario_sstt"})
        self.assertEqual(self.client.get(self.url,{"mes":"2026-11"}).context["cantidad"],2)

    def test_rechaza_privilegios_y_no_crea_usuario(self):
        self.usuario.is_staff=True;self.usuario.save()
        with self.assertRaises(CommandError):self.habilitar()
        self.assertFalse(self.usuario.groups.exists())
        with self.assertRaises(CommandError):
            call_command("habilitar_calendario_internos",usuario="inexistente",stdout=StringIO())
        self.assertEqual(User.objects.count(),1)

    def test_rechaza_otros_roles_sin_quitarlos(self):
        self.usuario.groups.add(Group.objects.get(name="Coordinador"))
        with self.assertRaises(CommandError):self.habilitar()
        self.assertFalse(self.usuario.groups.filter(name=GRUPO_INTERNOS).exists())
        self.assertTrue(self.usuario.groups.filter(name="Coordinador").exists())
