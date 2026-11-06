from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from .casos_uso.edicion_odt import editar_odt, revisar_odt, revisar_odts
from .dominio.errores import DatosODTInvalidos, ODTBloqueada, ODTNoEncontrada
from .dominio.servicios import SERVICIOS_PRINCIPALES
from .dominio.validacion_odt import numero_odt, importe_pago
from .facturacion_models import FacturacionContratista, FacturacionODT, PeriodoFacturacion
from .models import CorreccionODT, EventoCorreccionODT, EventoRevision, ODT, Revision


class ValidacionOperacionesTests(SimpleTestCase):
    def test_numero_formateado_admite_formatos_visibles(self):
        for valor in ("77527", "77.527", "77 527"):
            self.assertEqual(numero_odt(valor, formateado=True), 77527)

    def test_numero_no_extrae_digitos_de_otro_texto(self):
        for valor in ("ODT77527", "77x527", "-77527", "77,527", "1 2", "７７５２７", "", 0, None, "9"*100):
            with self.subTest(valor=valor), self.assertRaises(DatosODTInvalidos):
                numero_odt(valor, formateado=True)

    def test_monto_limites_nan_negativos_y_precision(self):
        self.assertEqual(importe_pago("0"), Decimal("0"))
        self.assertEqual(importe_pago("999999999999.99"), Decimal("999999999999.99"))
        for valor in ("NaN", "Infinity", "-1", "1000000000000", "1.001", "", None):
            with self.subTest(valor=valor), self.assertRaises(DatosODTInvalidos):
                importe_pago(valor)


class OperacionesODTTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("admin", password="prueba")
        self.odt = ODT.objects.create(numero=77527, servicio=SERVICIOS_PRINCIPALES[0],
            valor_pago_tecnico=100, contratista="Prueba")
        self.otra = ODT.objects.create(numero=77528, servicio=SERVICIOS_PRINCIPALES[0], valor_pago_tecnico=100)

    def editar(self, **datos):
        return editar_odt(self.user, **{
            "numero": self.odt.numero, "servicio": SERVICIOS_PRINCIPALES[0], "monto": "100", **datos,
        })

    def revisar(self, **datos):
        return revisar_odt(self.user, **{
            "numero": self.odt.numero, "estado": "EN_REVISION", "comentario": "Revisar antecedentes", **datos,
        })

    def facturar(self):
        periodo = PeriodoFacturacion.objects.create(fecha_desde="2026-10-21", fecha_hasta="2026-11-20")
        factura = FacturacionContratista.objects.create(periodo=periodo, contratista="Prueba")
        return FacturacionODT.objects.create(odt=self.odt, facturacion=factura,
            servicio_facturado=self.odt.servicio, monto_facturado=100)

    def test_editar_guarda_solo_diferencias_y_auditoria(self):
        r = self.editar(servicio=SERVICIOS_PRINCIPALES[1], monto="0", confirmar_monto=True, comentario="Ajuste")
        self.odt.refresh_from_db()
        self.assertTrue(r.cambio)
        self.assertEqual((self.odt.servicio, self.odt.valor_pago_tecnico), (SERVICIOS_PRINCIPALES[0], 100))
        self.assertEqual((self.odt.servicio_editado, self.odt.valor_pago_editado), (SERVICIOS_PRINCIPALES[1], 0))
        self.assertEqual(CorreccionODT.objects.get().estado, "PENDIENTE")
        self.assertEqual(EventoRevision.objects.get().usuario, self.user)
        self.assertIn("Motivo: Ajuste", EventoRevision.objects.get().comentario)
        self.assertEqual(EventoCorreccionODT.objects.count(), 1)
        self.assertFalse(Revision.objects.exists())

    def test_sin_cambio_no_crea_revision_seguimiento_ni_eventos(self):
        self.assertFalse(self.editar().cambio)
        self.assertEqual(CorreccionODT.objects.count(), 0)
        self.assertEqual(EventoRevision.objects.count(), 0)
        self.assertEqual(Revision.objects.count(), 0)

    def test_monto_requiere_confirmacion_explicita_booleana(self):
        for valor in (False, None, "SI", 1):
            with self.subTest(valor=valor), self.assertRaises(DatosODTInvalidos):
                self.editar(monto="50", confirmar_monto=valor)
        self.odt.refresh_from_db()
        self.assertIsNone(self.odt.valor_pago_editado)
        self.assertEqual(EventoRevision.objects.count(), 0)

    def test_repetir_edicion_no_duplica_historial(self):
        for _ in range(2):
            self.editar(monto="50", confirmar_monto=True)
        self.assertEqual(EventoRevision.objects.count(), 1)
        self.assertEqual(EventoCorreccionODT.objects.count(), 1)

    def test_volver_original_limpia_ediciones(self):
        self.editar(monto="50", confirmar_monto=True, servicio=SERVICIOS_PRINCIPALES[1])
        self.editar(confirmar_monto=True)
        self.odt.refresh_from_db()
        self.assertIsNone(self.odt.servicio_editado)
        self.assertIsNone(self.odt.valor_pago_editado)
        self.assertFalse(self.odt.modificado_manualmente)

    def test_servicio_historico_puede_conservarse_pero_no_inventarse(self):
        ODT.objects.filter(pk=self.odt.pk).update(servicio="Servicio histórico")
        self.editar(servicio="Servicio histórico", monto="50", confirmar_monto=True)
        with self.assertRaises(DatosODTInvalidos):
            self.editar(servicio="Otro inventado")

    def test_editar_no_modifica_revision_existente(self):
        revision = Revision.objects.create(odt=self.odt, estado="EN_REVISION", observacion="Motivo original")
        r = self.editar(monto="50", confirmar_monto=True)
        revision.refresh_from_db()
        self.assertEqual((revision.estado, revision.observacion), ("EN_REVISION", "Motivo original"))
        self.assertEqual(r.estado, "EN_REVISION")

    def test_pago_transiciones_y_rechazo_definitivo(self):
        self.revisar()
        self.revisar(estado="APROBADA", comentario="Validado")
        self.revisar(estado="RECHAZADA", comentario="Rechazo definitivo")
        with self.assertRaises(ODTBloqueada):
            self.revisar(estado="APROBADA")
        with self.assertRaises(ODTBloqueada):
            self.editar(monto="50", confirmar_monto=True)
        self.assertEqual(Revision.objects.get(odt=self.odt).estado, "RECHAZADA")
        self.assertEqual(EventoRevision.objects.count(), 3)

    def test_rechazo_y_revision_requieren_motivo(self):
        for estado in ("RECHAZADA", "EN_REVISION"):
            with self.subTest(estado=estado), self.assertRaises(DatosODTInvalidos):
                self.revisar(estado=estado, comentario="  ")
        self.assertFalse(Revision.objects.exists())

    def test_aprobacion_predeterminada_e_idempotencia_sin_eventos(self):
        self.assertFalse(self.revisar(estado="APROBADA", comentario="").cambio)
        Revision.objects.create(odt=self.odt, estado="POR_REVISAR")
        self.assertFalse(self.revisar(estado="APROBADA", comentario="").cambio)
        self.assertFalse(EventoRevision.objects.exists())

    def test_facturada_bloquea_edicion_y_revision(self):
        item = self.facturar()
        with self.assertRaises(ODTBloqueada):
            self.editar(monto="50", confirmar_monto=True)
        with self.assertRaises(ODTBloqueada):
            self.revisar()
        item.refresh_from_db()
        self.assertEqual(item.monto_facturado, 100)
        self.assertFalse(EventoRevision.objects.exists())

    def test_fallo_auditoria_revierte_edicion_y_seguimiento(self):
        with patch("revisiones.casos_uso.edicion_odt.EventoRevision.objects.create", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.editar(monto="50", confirmar_monto=True)
        self.odt.refresh_from_db()
        self.assertIsNone(self.odt.valor_pago_editado)
        self.assertFalse(CorreccionODT.objects.exists())
        self.assertFalse(EventoCorreccionODT.objects.exists())

    def test_fallo_auditoria_revierte_revision(self):
        with patch("revisiones.casos_uso.edicion_odt.EventoRevision.objects.create", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.revisar()
        self.assertFalse(Revision.objects.exists())

    def test_revision_multiple_valida_todas_antes_de_guardar(self):
        Revision.objects.create(odt=self.otra, estado="RECHAZADA")
        with self.assertRaises(ODTBloqueada):
            revisar_odts(self.user, numeros=[self.odt.numero, self.otra.numero], estado="EN_REVISION", comentario="Motivo")
        self.assertFalse(Revision.objects.filter(odt=self.odt).exists())
        self.assertFalse(EventoRevision.objects.exists())

    def test_revision_multiple_no_ignora_numeros_invalidos_o_inexistentes(self):
        for seleccion, error in (([self.odt.numero, "mal"], DatosODTInvalidos),
                                 ([self.odt.numero, 999], ODTNoEncontrada)):
            with self.subTest(seleccion=seleccion), self.assertRaises(error):
                revisar_odts(self.user, numeros=seleccion, estado="EN_REVISION", comentario="Motivo")
        self.assertFalse(Revision.objects.exists())

    def test_revision_multiple_deduplica_y_comparte_idempotencia(self):
        argumentos = dict(numeros=[self.odt.numero, self.otra.numero, self.odt.numero],
            estado="EN_REVISION", comentario="Motivo común")
        self.assertEqual(revisar_odts(self.user, **argumentos), 2)
        self.assertEqual(revisar_odts(self.user, **argumentos), 0)
        self.assertEqual(EventoRevision.objects.count(), 2)

    def test_revision_multiple_fallo_intermedio_revierte_todo(self):
        crear = EventoRevision.objects.create
        llamadas = []
        def fallar_segunda(**kwargs):
            llamadas.append(kwargs)
            if len(llamadas) == 2:
                raise RuntimeError("Fallo simulado")
            return crear(**kwargs)
        with patch("revisiones.casos_uso.edicion_odt.EventoRevision.objects.create", side_effect=fallar_segunda):
            with self.assertRaises(RuntimeError):
                revisar_odts(self.user, numeros=[self.odt.numero, self.otra.numero], estado="EN_REVISION", comentario="Motivo")
        self.assertFalse(Revision.objects.exists())
        self.assertFalse(EventoRevision.objects.exists())

    def test_revision_multiple_limites_y_tipo_seleccion(self):
        for seleccion in ([], None, "77527", 77527, list(range(1, 302))):
            with self.subTest(seleccion=type(seleccion)), self.assertRaises(DatosODTInvalidos):
                revisar_odts(self.user, numeros=seleccion, estado="EN_REVISION", comentario="Motivo")

    def test_permiso_se_exige_sin_pasar_por_vistas(self):
        for usuario in (AnonymousUser(), User.objects.create_user("sin_permiso")):
            with self.subTest(usuario=str(usuario)), self.assertRaises(PermissionDenied):
                editar_odt(usuario, numero=self.odt.numero, servicio=SERVICIOS_PRINCIPALES[0], monto=100)
            with self.assertRaises(PermissionDenied):
                revisar_odt(usuario, numero=self.odt.numero, estado="APROBADA")

    def test_coordinador_no_puede_saltar_middleware_aunque_tenga_permiso(self):
        usuario = User.objects.create_user("coordinador_prueba")
        usuario.groups.add(Group.objects.get_or_create(name="Coordinador")[0])
        ct = ContentType.objects.get_for_model(ODT)
        for codigo in ("editar_odt_sstt", "revisar_pago_sstt"):
            permiso, _ = Permission.objects.get_or_create(content_type=ct, codename=codigo)
            usuario.user_permissions.add(permiso)
        with self.assertRaises(PermissionDenied):
            editar_odt(usuario, numero=self.odt.numero, servicio=SERVICIOS_PRINCIPALES[0], monto=100)
        with self.assertRaises(PermissionDenied):
            revisar_odt(usuario, numero=self.odt.numero, estado="APROBADA")

    def test_http_conserva_json_metodo_y_estados_de_error(self):
        self.client.force_login(self.user)
        url = reverse("guardar_fila")
        self.assertEqual(self.client.get(url).status_code, 405)
        datos = {"numero": self.odt.numero, "servicio": SERVICIOS_PRINCIPALES[0], "monto": "100"}
        self.assertEqual(self.client.post(url, datos).json()["mensaje"], "No hay cambios para guardar.")
        self.assertEqual(self.client.post(url, {**datos, "numero": 999}).status_code, 404)
        self.assertEqual(self.client.post(url, {**datos, "monto": "NaN"}).status_code, 400)
        self.facturar()
        self.assertEqual(self.client.post(url, datos).status_code, 409)

    def test_http_editar_no_cambia_estado_enviado_en_el_formulario(self):
        self.client.force_login(self.user)
        respuesta = self.client.post(reverse("guardar_fila"), {
            "numero": self.odt.numero, "servicio": SERVICIOS_PRINCIPALES[1], "monto": "100", "estado": "RECHAZADA",
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["estado"], "APROBADA")
        self.assertFalse(Revision.objects.exists())

    def test_http_revision_formateada_y_no_refleja_entradas_invalidas(self):
        self.client.force_login(self.user)
        url = reverse("actualizar_revision")
        r = self.client.post(url, {"numero": "77 527", "estado": "EN_REVISION", "comentario": "Motivo"})
        self.assertEqual(r.json()["estado"], "EN_REVISION")
        r = self.client.post(url, {"numero": "ODT77527", "estado": "APROBADA"})
        self.assertEqual(r.status_code, 400)
        self.assertNotIn("ODT77527", r.content.decode())

    def test_permiso_revisar_no_otorga_editar(self):
        usuario = User.objects.create_user("revisor_prueba")
        ct = ContentType.objects.get_for_model(ODT)
        permiso, _ = Permission.objects.get_or_create(content_type=ct, codename="revisar_pago_sstt")
        usuario.user_permissions.add(permiso)
        self.assertTrue(revisar_odt(usuario, numero=self.odt.numero,
            estado="EN_REVISION", comentario="Revisado").cambio)
        with self.assertRaises(PermissionDenied):
            editar_odt(usuario, numero=self.odt.numero, servicio=SERVICIOS_PRINCIPALES[0], monto=100)

    def test_http_exige_csrf_sin_hacer_escrituras(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.user)
        respuesta = cliente.post(reverse("actualizar_revision"), {
            "numero": self.odt.numero, "estado": "EN_REVISION", "comentario": "Motivo",
        })
        self.assertEqual(respuesta.status_code, 403)
        self.assertFalse(Revision.objects.exists())

    def test_http_revision_multiple_redirige_y_audita(self):
        self.client.force_login(self.user)
        respuesta = self.client.post(reverse("acciones"), {
            "odts": [str(self.odt.numero), str(self.otra.numero)],
            "nuevo_estado": "EN_REVISION", "comentario": "Motivo común",
        })
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(respuesta.url, reverse("bandeja"))
        self.assertEqual(Revision.objects.filter(estado="EN_REVISION").count(), 2)
        self.assertEqual(EventoRevision.objects.count(), 2)
