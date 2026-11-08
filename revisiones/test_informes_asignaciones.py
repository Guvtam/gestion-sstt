from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .casos_uso.informes_asignaciones import actualizar_estado_informe, asignar_responsable
from .coordinadores_softguard import COORDINADORES_SOFTGUARD, identificar_coordinador_odt
from .dominio.errores import DatosODTInvalidos, ODTBloqueada, ODTNoEncontrada, VerificacionCoordinadorFallida
from .facturacion_models import FacturacionContratista, FacturacionODT, PeriodoFacturacion
from .models import AsignacionCoordinadorODT, EventoRevision, ODT, Revision


class InformesAsignacionesTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", password="prueba")
        self.autorizado = User.objects.create_user("jiturriaga")
        self.ids = list(COORDINADORES_SOFTGUARD)
        self.datos = [COORDINADORES_SOFTGUARD[n] for n in self.ids]
        self.coord = User.objects.create_user(self.datos[0]["usuario"])
        self.odt = ODT.objects.create(numero=1, servicio="Servicio de prueba", valor_pago_tecnico=100)
        self.otra = ODT.objects.create(numero=2, servicio="Servicio de prueba", valor_pago_tecnico=100)
        self.permitir(self.coord, "cambiar_informe_sstt")

    def permitir(self, usuario, codigo):
        ct = ContentType.objects.get_for_model(ODT)
        permiso, _ = Permission.objects.get_or_create(content_type=ct, codename=codigo)
        usuario.user_permissions.add(permiso)

    def informe(self, usuario=None, **opciones):
        datos = {"numero": 1, "estado": "ENVIADO", **opciones}
        return actualizar_estado_informe(usuario or self.admin, **datos)

    def asignar(self, usuario=None, **opciones):
        datos = {"numero": 1, "coordinador": self.datos[0]["usuario"],
                 "verificar_origen": lambda n: {"identificado": False}, **opciones}
        return asignar_responsable(usuario or self.admin, **datos)

    def facturar(self):
        periodo = PeriodoFacturacion.objects.create(fecha_desde="2026-10-21", fecha_hasta="2026-11-20")
        factura = FacturacionContratista.objects.create(periodo=periodo, contratista="Prueba")
        return FacturacionODT.objects.create(odt=self.odt, facturacion=factura,
            servicio_facturado="Instantánea", monto_facturado=100)

    def eventos(self, numeros, usuarios):
        return [{"NumeroODT": n, "IDUsuario": self.ids[0 if n == 1 else 1],
                 "FechaHora": timezone.now(), "Accion": "ALTA"} for n in numeros]

    def test_informe_guarda_estado_actor_fecha_y_evento_sin_cambiar_pago(self):
        revision = Revision.objects.create(odt=self.odt, estado="EN_REVISION", observacion="Motivo pago")
        resultado = self.informe()
        self.odt.refresh_from_db()
        revision.refresh_from_db()
        self.assertTrue(resultado.cambio)
        self.assertEqual(self.odt.estado_informe, "ENVIADO")
        self.assertEqual(self.odt.informe_actualizado_por, self.admin)
        self.assertIsNotNone(self.odt.informe_actualizado_en)
        self.assertEqual((revision.estado, revision.observacion), ("EN_REVISION", "Motivo pago"))
        evento = EventoRevision.objects.get()
        self.assertEqual((evento.estado_anterior, evento.estado_nuevo), ("EN_REVISION", "EN_REVISION"))
        self.assertEqual(evento.comentario, "Informe: No enviado → Enviado")

    def test_informe_heredado_por_revisar_se_audita_como_aprobado(self):
        Revision.objects.create(odt=self.odt, estado="POR_REVISAR")
        self.informe()
        self.assertEqual(EventoRevision.objects.get().estado_nuevo, "APROBADA")
        self.assertEqual(Revision.objects.get().estado, "POR_REVISAR")

    def test_informe_sin_cambios_no_duplica_evento_o_fecha(self):
        self.informe()
        self.odt.refresh_from_db()
        fecha = self.odt.informe_actualizado_en
        self.assertFalse(self.informe().cambio)
        self.odt.refresh_from_db()
        self.assertEqual(self.odt.informe_actualizado_en, fecha)
        self.assertEqual(EventoRevision.objects.count(), 1)

    def test_informe_admite_los_tres_estados(self):
        for estado in ("ENVIADO", "NO_APLICA", "NO_ENVIADO"):
            self.informe(estado=estado)
            self.odt.refresh_from_db()
            self.assertEqual(self.odt.estado_informe, estado)

    def test_informe_facturado_o_rechazado_bloqueado_incluso_sin_cambios(self):
        self.facturar()
        with self.assertRaises(ODTBloqueada):
            self.informe(estado="NO_ENVIADO")
        FacturacionODT.objects.all().delete()
        Revision.objects.create(odt=self.odt, estado="RECHAZADA")
        with self.assertRaises(ODTBloqueada):
            self.informe()
        self.assertFalse(EventoRevision.objects.exists())

    def test_informe_validacion_y_odt_inexistente(self):
        for datos in ({"numero": "1x"}, {"numero": 0}, {"estado": "OTRO"}):
            with self.subTest(datos=datos), self.assertRaises(DatosODTInvalidos):
                self.informe(**datos)
        with self.assertRaises(ODTNoEncontrada):
            self.informe(numero=999)

    def test_informe_permiso_exigido_sin_vista(self):
        for usuario in (AnonymousUser(), User.objects.create_user("sin_permiso")):
            with self.subTest(usuario=str(usuario)), self.assertRaises(PermissionDenied):
                self.informe(usuario)

    def test_informe_coordinador_solo_propias_y_no_sin_identificar(self):
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores", side_effect=self.eventos):
            self.informe(self.coord)
            with self.assertRaises(PermissionDenied):
                self.informe(self.coord, numero=2)
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores", return_value=[]):
            with self.assertRaises(PermissionDenied):
                self.informe(self.coord)

    def test_informe_coordinador_desvinculado_no_consulta_origen(self):
        usuario = User.objects.create_user("coordinador_prueba")
        usuario.groups.add(Group.objects.get_or_create(name="Coordinador")[0])
        self.permitir(usuario, "cambiar_informe_sstt")
        with patch("revisiones.casos_uso.autorizacion.identificar_coordinadores_odt") as consultar:
            with self.assertRaises(PermissionDenied):
                self.informe(usuario)
        consultar.assert_not_called()

    def test_informe_fallo_origen_no_da_permiso_y_oculta_detalle(self):
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores", side_effect=RuntimeError("secreto-inventado")):
            with self.assertRaises(VerificacionCoordinadorFallida) as error:
                self.informe(self.coord)
        self.assertNotIn("secreto-inventado", str(error.exception))
        self.assertFalse(EventoRevision.objects.exists())

    def test_informe_responsable_malformado_o_no_disponible_no_autoriza(self):
        for info in (None, {}, {"identificado": "True"},
                     {"identificado": True, "usuario": self.datos[0]["usuario"], "disponible": False}):
            with self.subTest(info=info), self.assertRaises(VerificacionCoordinadorFallida):
                self.informe(self.coord, resolver_responsable=lambda n: info)
        self.assertFalse(EventoRevision.objects.exists())

    def test_informe_fallo_evento_revierte_estado_autor_y_fecha(self):
        with patch("revisiones.casos_uso.informes_asignaciones.EventoRevision.objects.create", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.informe()
        self.odt.refresh_from_db()
        self.assertEqual(self.odt.estado_informe, "NO_ENVIADO")
        self.assertIsNone(self.odt.informe_actualizado_por)
        self.assertIsNone(self.odt.informe_actualizado_en)

    def test_asignacion_conserva_regla_admin_y_usuario_autorizado(self):
        for usuario in (User.objects.create_user("otro"), User.objects.create_superuser("super_otro", password="prueba"), AnonymousUser()):
            with self.subTest(usuario=str(usuario)), self.assertRaises(PermissionDenied):
                self.asignar(usuario)
        self.asignar(self.autorizado)
        asignacion = AsignacionCoordinadorODT.objects.get()
        self.assertEqual(asignacion.asignado_por, self.autorizado)
        self.assertEqual(asignacion.usuario_coordinador, self.datos[0]["usuario"])
        self.assertEqual(EventoRevision.objects.get().usuario, self.autorizado)
        self.assertEqual(identificar_coordinador_odt(1)["usuario"], self.datos[0]["usuario"])

    def test_usuario_asignador_inactivo_denegado(self):
        self.autorizado.is_active = False
        with self.assertRaises(PermissionDenied):
            self.asignar(self.autorizado)

    def test_asignacion_invalida_o_odt_inexistente_no_escribe(self):
        with self.assertRaises(DatosODTInvalidos):
            self.asignar(coordinador="no_configurado")
        with self.assertRaises(ODTNoEncontrada):
            self.asignar(numero=999)
        self.assertFalse(AsignacionCoordinadorODT.objects.exists())

    def test_asignacion_no_sobrescribe_local_ni_consulta_sql_de_nuevo(self):
        self.asignar()
        with patch("revisiones.casos_uso.informes_asignaciones.identificar_coordinador_softguard") as consulta:
            with self.assertRaises(ODTBloqueada):
                self.asignar(coordinador=self.datos[1]["usuario"], verificar_origen=consulta)
        consulta.assert_not_called()
        self.assertEqual(EventoRevision.objects.count(), 1)

    def test_asignacion_responsable_de_origen_no_se_reemplaza(self):
        with self.assertRaises(ODTBloqueada):
            self.asignar(verificar_origen=lambda n: {"identificado": True})
        self.assertFalse(AsignacionCoordinadorODT.objects.exists())

    def test_asignacion_fallo_o_respuesta_inesperada_no_es_sin_identificar(self):
        for info in (None, {}, {"identificado": "False"}):
            with self.subTest(info=info), self.assertRaises(VerificacionCoordinadorFallida):
                self.asignar(verificar_origen=lambda n: info)
        with patch("revisiones.casos_uso.informes_asignaciones.identificar_coordinador_softguard", side_effect=RuntimeError("secreto-inventado")):
            with self.assertRaises(VerificacionCoordinadorFallida) as error:
                self.asignar(verificar_origen=None)
        self.assertNotIn("secreto-inventado", str(error.exception))
        self.assertFalse(AsignacionCoordinadorODT.objects.exists())

    def test_asignacion_revalida_cambio_local_durante_verificacion(self):
        def verificar(numero):
            AsignacionCoordinadorODT.objects.create(odt=self.odt, usuario_coordinador=self.datos[1]["usuario"])
            return {"identificado": False}
        with self.assertRaises(ODTBloqueada):
            self.asignar(verificar_origen=verificar)
        self.assertEqual(AsignacionCoordinadorODT.objects.get().usuario_coordinador, self.datos[1]["usuario"])
        self.assertFalse(EventoRevision.objects.exists())

    def test_asignacion_fallo_auditoria_revierte_asignacion(self):
        with patch("revisiones.casos_uso.informes_asignaciones.EventoRevision.objects.create", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.asignar()
        self.assertFalse(AsignacionCoordinadorODT.objects.exists())
        self.assertFalse(EventoRevision.objects.exists())

    def test_asignacion_metadata_no_cambia_facturacion_o_pago_rechazado(self):
        item = self.facturar()
        Revision.objects.create(odt=self.odt, estado="RECHAZADA", observacion="Decisión previa")
        self.asignar()
        item.refresh_from_db()
        self.assertEqual((item.servicio_facturado, item.monto_facturado), ("Instantánea", 100))
        self.assertEqual(Revision.objects.get().estado, "RECHAZADA")

    def test_http_informe_coord_reutiliza_verificacion_de_middleware(self):
        self.client.force_login(self.coord)
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores", side_effect=self.eventos) as origen:
            respuesta = self.client.post(reverse("actualizar_informe"), {"numero": 1, "estado": "ENVIADO"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["mensaje"], "Estado de informe actualizado.")
        self.assertEqual(origen.call_count, 1)

    def test_http_informe_estados_400_404_409_y_503(self):
        self.client.force_login(self.admin)
        url = reverse("actualizar_informe")
        self.assertEqual(self.client.post(url, {"numero": 0, "estado": "ENVIADO"}).status_code, 400)
        self.assertEqual(self.client.post(url, {"numero": 999, "estado": "ENVIADO"}).status_code, 404)
        self.facturar()
        self.assertEqual(self.client.post(url, {"numero": 1, "estado": "ENVIADO"}).status_code, 409)
        self.client.force_login(self.coord)
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores", side_effect=RuntimeError):
            self.assertEqual(self.client.post(url, {"numero": 2, "estado": "ENVIADO"}).status_code, 503)

    def test_http_coordinador_no_puede_editar_informe_ajeno(self):
        self.client.force_login(self.coord)
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores", side_effect=self.eventos):
            r = self.client.post(reverse("actualizar_informe"), {"numero": 2, "estado": "ENVIADO"})
        self.assertEqual(r.status_code, 403)
        self.otra.refresh_from_db()
        self.assertEqual(self.otra.estado_informe, "NO_ENVIADO")

    def test_http_numero_invalido_de_coordinador_es_400_sin_consultar_sql(self):
        self.client.force_login(self.coord)
        with patch("revisiones.coordinadores_softguard.consultar_eventos_coordinadores") as origen:
            for numero in ("-1", "0", "ODT1"):
                r = self.client.post(reverse("actualizar_informe"), {"numero": numero, "estado": "ENVIADO"})
                self.assertEqual(r.status_code, 400)
        origen.assert_not_called()

    def test_http_csrf_y_post_siguen_obligatorios(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.admin)
        for ruta in ("actualizar_informe", "asignar_coordinador"):
            self.assertEqual(cliente.get(reverse(ruta)).status_code, 405)
            self.assertEqual(cliente.post(reverse(ruta), {"numero": 1}).status_code, 403)
        self.assertFalse(EventoRevision.objects.exists())

    def test_http_asignacion_preserva_respuesta_y_conflicto(self):
        self.client.force_login(self.admin)
        datos = {"numero": 1, "coordinador": self.datos[0]["usuario"]}
        with patch("revisiones.vistas.operaciones_odt.identificar_coordinador_softguard", return_value={"identificado": False}):
            r = self.client.post(reverse("asignar_coordinador"), datos)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"ok": True, "coordinador": self.datos[0]["nombre"]})
        self.assertEqual(self.client.post(reverse("asignar_coordinador"), datos).status_code, 409)
