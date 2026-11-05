from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import include, path
from django.http import HttpResponse
from revisiones.models import ODT
from .models import Contratista, EquivalenciaSoftGuard
from .vinculacion import propuestas_vinculacion, guardar_propuesta, aplicar_exactas

urlpatterns = [
    path("contratistas/", include("contratistas.urls")),
    path("logout/", lambda r: HttpResponse(), name="logout"),
]

@override_settings(ROOT_URLCONF=__name__)
class VinculacionTests(TestCase):
    def setUp(self):
        self.c = Contratista.objects.create(nombre="José Álvarez", nombre_empresa="Empresa Prueba")
        self.odt = ODT.objects.create(numero=1, tecnico="T. EXTERNO - jose alvarez")
        self.admin = get_user_model().objects.create_superuser("admin", password="test")

    def test_exactas_normalizadas_y_repeticion(self):
        self.assertTrue(propuestas_vinculacion()[0]["automatico"])
        self.assertEqual(aplicar_exactas(), 1)
        self.assertEqual(aplicar_exactas(), 0)
        self.assertEqual(EquivalenciaSoftGuard.objects.get().contratista, self.c)
        self.odt.refresh_from_db()
        self.assertEqual(self.odt.tecnico, "T. EXTERNO - jose alvarez")

    def test_parcial_requiere_confirmacion(self):
        self.c.nombre = "José Álvarez Fuentes"
        self.c.save()
        propuesta = propuestas_vinculacion()[0]
        self.assertFalse(propuesta["automatico"])
        self.assertEqual(aplicar_exactas(), 0)
        self.assertTrue(guardar_propuesta(self.odt.tecnico, self.c.pk))

    def test_homonimos_son_ambiguos(self):
        Contratista.objects.create(nombre="Jose Alvarez")
        p = propuestas_vinculacion()[0]
        self.assertEqual(p["estado"], "Ambigua")
        self.assertEqual(aplicar_exactas(), 0)

    def test_existente_nunca_se_reasigna(self):
        otro = Contratista.objects.create(nombre="Otro")
        e = EquivalenciaSoftGuard.objects.create(contratista=otro, nombre_softguard=self.odt.tecnico)
        self.assertEqual(propuestas_vinculacion(), [])
        self.assertFalse(guardar_propuesta(self.odt.tecnico, self.c.pk))
        e.refresh_from_db()
        self.assertEqual(e.contratista, otro)

    def test_no_vincula_inactivos_o_nombres_inventados(self):
        self.c.activo = False
        self.c.save()
        self.assertEqual(aplicar_exactas(), 0)
        with self.assertRaises(ValueError):
            guardar_propuesta("T. EXTERNO - Inventado", self.c.pk)

    def test_reserva_manual_previa_se_conserva(self):
        Contratista.objects.create(nombre="Otro", nombre_softguard=self.odt.tecnico, activo=False)
        self.assertTrue(propuestas_vinculacion()[0]["reservado"])
        self.assertEqual(aplicar_exactas(), 0)

    def test_no_aplica_exacta_si_cambio_candidato(self):
        p = propuestas_vinculacion()[0]
        self.c.nombre = "José Álvarez Fuentes"
        self.c.save()
        with self.assertRaises(ValueError):
            guardar_propuesta(p["nombre"], self.c.pk, solo_exacta=True)

    def test_permiso_y_get_sin_mutacion(self):
        self.client.force_login(self.admin)
        respuesta = self.client.get("/contratistas/vinculacion-softguard/")
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Vincular todas las exactas")
        self.assertEqual(EquivalenciaSoftGuard.objects.count(), 0)
        usuario = get_user_model().objects.create_user("lectura")
        self.client.force_login(usuario)
        self.assertEqual(self.client.post("/contratistas/vinculacion-softguard/", {"accion":"exactas"}).status_code, 403)

    def test_post_crea_equivalencias(self):
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory
        from .views import vinculacion_softguard
        request = RequestFactory().post("/", {"accion": "exactas"})
        request.user = self.admin
        request.session = {}
        request._messages = FallbackStorage(request)
        self.assertEqual(vinculacion_softguard(request).status_code, 302)
        self.assertEqual(EquivalenciaSoftGuard.objects.count(), 1)
