from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
import time

from django.contrib.auth.models import AnonymousUser, Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from .casos_uso.facturacion import actualizar_requisicion, confirmar, previsualizar
from .consultas.facturacion import odts_facturables
from .dominio.facturacion import FacturacionInvalida, FacturacionNoEncontrada, SeleccionFacturacion
from .dominio.servicios import SERVICIOS_PRINCIPALES
from .facturacion_models import FacturacionContratista, FacturacionODT, PeriodoFacturacion
from .models import ODT, Revision


class PeriodoFacturacionTests(SimpleTestCase):
    def test_periodos_incluyendo_cambio_de_anio(self):
        for desde, hasta in ((date(2026, 10, 21), date(2026, 11, 20)),
                             (date(2026, 12, 21), date(2027, 1, 20))):
            self.assertEqual(SeleccionFacturacion(desde, hasta).desde, desde)

    def test_periodos_incompletos_o_arbitrarios_no_se_admiten(self):
        for desde, hasta in ((None, date(2026, 11, 20)),
                             (date(2026, 10, 1), date(2026, 11, 20)),
                             (date(2026, 10, 21), date(2026, 11, 21)),
                             (date(9999, 12, 21), date(9999, 12, 31))):
            with self.subTest(desde=desde), self.assertRaises(FacturacionInvalida):
                SeleccionFacturacion(desde, hasta)


class ConfirmacionFacturacionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("admin", password="prueba")
        self.fecha = timezone.make_aware(datetime(2026, 10, 25, 12))
        self.seleccion = SeleccionFacturacion(date(2026, 10, 21), date(2026, 11, 20))
        for n, contratista in ((1, "Prueba A"), (2, "Prueba A"), (3, "Prueba B")):
            ODT.objects.create(numero=n, contratista=contratista, cuenta_completa=f"FIR-{n}",
                servicio=SERVICIOS_PRINCIPALES[0], valor_pago_tecnico=100,
                estado_softguard="Finalizado", fecha_finalizacion=self.fecha)

    def confirmar(self, vista=None, seleccion=None, **opciones):
        seleccion = seleccion or self.seleccion
        vista = vista or previsualizar(self.user, seleccion)
        return confirmar(self.user, seleccion,
            requisiciones=opciones.get("requisiciones", {g["contratista"]: "REQ-PRUEBA" for g in vista.resumen}),
            confirmacion=opciones.get("confirmacion", vista.confirmacion))

    def test_resumen_y_confirmacion_guardan_instantanea_efectiva(self):
        ODT.objects.filter(numero=1).update(servicio_editado=SERVICIOS_PRINCIPALES[1], valor_pago_editado=0)
        vista = previsualizar(self.user, self.seleccion)
        self.assertEqual(vista.cantidad, 3)
        self.assertEqual([g["monto"] for g in vista.resumen], [Decimal("100"), Decimal("100")])
        resultado = self.confirmar(vista)
        self.assertEqual((resultado.cantidad_odt, resultado.cantidad_contratistas), (3, 2))
        item = FacturacionODT.objects.get(odt__numero=1)
        self.assertEqual((item.servicio_facturado, item.monto_facturado), (SERVICIOS_PRINCIPALES[1], 0))
        self.assertEqual(item.facturacion.creado_por, self.user)
        self.assertEqual(item.facturacion.periodo.creado_por, self.user)

    def test_cambiar_monto_mismo_conteo_rechaza_sin_crear_periodo(self):
        vista = previsualizar(self.user, self.seleccion)
        ODT.objects.filter(numero=1).update(valor_pago_editado=50)
        with self.assertRaises(FacturacionInvalida):
            self.confirmar(vista)
        self.assertFalse(PeriodoFacturacion.objects.exists())

    def test_cambiar_servicio_mismo_conteo_rechaza(self):
        vista = previsualizar(self.user, self.seleccion)
        ODT.objects.filter(numero=1).update(servicio_editado=SERVICIOS_PRINCIPALES[1])
        with self.assertRaises(FacturacionInvalida):
            self.confirmar(vista)
        self.assertFalse(FacturacionODT.objects.exists())

    def test_sustituir_odt_por_otra_igual_cantidad_y_monto_no_pasa(self):
        vista = previsualizar(self.user, self.seleccion)
        ODT.objects.filter(numero=1).update(estado_softguard="Pendiente")
        ODT.objects.create(numero=4, contratista="Prueba A", cuenta_completa="FIR-4",
            servicio=SERVICIOS_PRINCIPALES[0], valor_pago_tecnico=100,
            estado_softguard="Finalizado", fecha_finalizacion=self.fecha)
        with self.assertRaises(FacturacionInvalida):
            self.confirmar(vista)

    def test_cambiar_contratista_rechaza_sin_asociar_requisiciones_a_otro(self):
        vista = previsualizar(self.user, self.seleccion)
        ODT.objects.filter(numero=1).update(contratista="Prueba B")
        with self.assertRaises(FacturacionInvalida):
            self.confirmar(vista)
        self.assertFalse(FacturacionContratista.objects.exists())

    def test_firma_faltante_manipulada_o_de_otro_usuario_no_confirma(self):
        vista = previsualizar(self.user, self.seleccion)
        for firma in ("", vista.confirmacion + "x"):
            with self.subTest(firma=firma[-5:]), self.assertRaises(FacturacionInvalida):
                self.confirmar(vista, confirmacion=firma)
        otro = User.objects.create_superuser("otro_admin", password="prueba")
        with self.assertRaises(FacturacionInvalida):
            confirmar(otro, self.seleccion, requisiciones={"Prueba A": "", "Prueba B": ""}, confirmacion=vista.confirmacion)
        self.assertFalse(FacturacionODT.objects.exists())

    def test_confirmacion_vencida_requiere_previsualizar_de_nuevo(self):
        vista = previsualizar(self.user, self.seleccion)
        with patch("django.core.signing.time.time", return_value=time.time()+1900):
            with self.assertRaises(FacturacionInvalida):
                self.confirmar(vista)

    def test_filtros_no_se_pueden_cambiar_reutilizando_confirmacion(self):
        vista = previsualizar(self.user, self.seleccion)
        filtrada = replace(self.seleccion, contratistas=("Prueba A",))
        with self.assertRaises(FacturacionInvalida):
            self.confirmar(vista, seleccion=filtrada)

    def test_vacio_no_crea_periodo(self):
        vacia = replace(self.seleccion, contratistas_filtrados=True)
        vista = previsualizar(self.user, vacia)
        self.assertEqual(vista.cantidad, 0)
        with self.assertRaises(FacturacionInvalida):
            self.confirmar(vista, seleccion=vacia)
        self.assertFalse(PeriodoFacturacion.objects.exists())

    def test_repetir_confirmacion_no_duplica_facturas(self):
        vista = previsualizar(self.user, self.seleccion)
        self.confirmar(vista)
        with self.assertRaises(FacturacionInvalida):
            self.confirmar(vista)
        self.assertEqual((FacturacionODT.objects.count(), FacturacionContratista.objects.count()), (3, 2))

    def test_requisiciones_tienen_que_corresponder_a_los_contratistas(self):
        for requisiciones in ({"Otro": "REQ"}, {"Prueba A": "x"*101, "Prueba B": ""}):
            with self.subTest(requisiciones=requisiciones), self.assertRaises(FacturacionInvalida):
                self.confirmar(requisiciones=requisiciones)
        self.assertFalse(PeriodoFacturacion.objects.exists())

    def test_reutilizar_factura_no_sobrescribe_requisicion(self):
        periodo = PeriodoFacturacion.objects.create(fecha_desde=self.seleccion.desde, fecha_hasta=self.seleccion.hasta)
        FacturacionContratista.objects.create(periodo=periodo, contratista="Prueba A", numero_requisicion="ANTERIOR")
        self.confirmar(requisiciones={"Prueba A": "NUEVA", "Prueba B": ""})
        self.assertEqual(FacturacionContratista.objects.get(contratista="Prueba A").numero_requisicion, "ANTERIOR")
        self.assertEqual(PeriodoFacturacion.objects.count(), 1)

    def test_fallo_guardando_items_revierte_cabeceras_y_periodo(self):
        def fallo_despues_de_escribir(items, **kwargs):
            items[0].save()
            raise IntegrityError("Fallo simulado después de la primera inserción")
        with patch("revisiones.casos_uso.facturacion.FacturacionODT.objects.bulk_create", side_effect=fallo_despues_de_escribir):
            with self.assertRaises(FacturacionInvalida):
                self.confirmar()
        self.assertFalse(PeriodoFacturacion.objects.exists())
        self.assertFalse(FacturacionContratista.objects.exists())
        self.assertFalse(FacturacionODT.objects.exists())

    def test_aprobacion_efectiva_finalizacion_y_filtro_servicio_editado(self):
        Revision.objects.create(odt=ODT.objects.get(numero=1), estado="POR_REVISAR")
        Revision.objects.create(odt=ODT.objects.get(numero=2), estado="EN_REVISION")
        ODT.objects.filter(numero=1).update(servicio_editado=SERVICIOS_PRINCIPALES[1])
        ODT.objects.filter(numero=3).update(estado_softguard="Pendiente")
        seleccion = replace(self.seleccion, servicios=(SERVICIOS_PRINCIPALES[1],))
        self.assertEqual(list(odts_facturables(seleccion).values_list("numero", flat=True)), [1])

    def test_limites_fecha_local_y_exclusion_dia_siguiente(self):
        limite = timezone.make_aware(datetime(2026, 11, 20, 23, 59, 59))
        ODT.objects.filter(numero=1).update(fecha_finalizacion=limite)
        ODT.objects.filter(numero=2).update(fecha_finalizacion=limite+timedelta(seconds=1))
        self.assertEqual(set(odts_facturables(self.seleccion).values_list("numero", flat=True)), {1, 3})

    def test_permiso_se_comprueba_antes_de_leer_o_escribir(self):
        for usuario in (AnonymousUser(), User.objects.create_user("sin_permiso")):
            with self.subTest(usuario=str(usuario)), self.assertRaises(PermissionDenied):
                previsualizar(usuario, self.seleccion)
            with self.assertRaises(PermissionDenied):
                confirmar(usuario, self.seleccion, requisiciones={}, confirmacion="")

    def test_coordinador_no_puede_invocar_operacion_aunque_tenga_permiso(self):
        usuario = User.objects.create_user("coordinador_prueba")
        usuario.groups.add(Group.objects.get_or_create(name="Coordinador")[0])
        ct = ContentType.objects.get_for_model(ODT)
        permiso, _ = Permission.objects.get_or_create(content_type=ct, codename="exportar_pagos_sstt")
        usuario.user_permissions.add(permiso)
        with self.assertRaises(PermissionDenied):
            previsualizar(usuario, self.seleccion)

    def test_modificar_requisicion_separadamente_y_dejar_pendiente(self):
        self.confirmar()
        factura = FacturacionContratista.objects.first()
        r = actualizar_requisicion(self.user, facturacion_id=factura.pk, numero=" REQ-EDITADA ")
        self.assertEqual(r.numero, "REQ-EDITADA")
        actualizar_requisicion(self.user, facturacion_id=factura.pk, numero="")
        factura.refresh_from_db()
        self.assertEqual(factura.numero_requisicion, "")
        with self.assertRaises(FacturacionInvalida):
            actualizar_requisicion(self.user, facturacion_id=factura.pk, numero="x"*101)
        with self.assertRaises(FacturacionNoEncontrada):
            actualizar_requisicion(self.user, facturacion_id=99999, numero="REQ")

    def test_http_previsualiza_y_confirma_con_el_mismo_contrato_visible(self):
        self.client.force_login(self.user)
        url = reverse("facturacion_previsualizar")
        parametros = {"fecha_desde": "2026-10-21", "fecha_hasta": "2026-11-20"}
        previa = self.client.get(url, parametros)
        self.assertEqual(previa.status_code, 200)
        self.assertEqual(previa.context["cantidad_odt"], 3)
        self.assertContains(previa, 'name="confirmacion_facturacion"')
        confirmada = self.client.post(url, {**parametros,
            "confirmacion_facturacion": previa.context["confirmacion_facturacion"],
            "requisicion_0": "REQ-A", "requisicion_1": "REQ-B",
        })
        self.assertEqual(confirmada.status_code, 302)
        self.assertEqual(FacturacionODT.objects.count(), 3)
        self.assertEqual(FacturacionContratista.objects.get(contratista="Prueba A").numero_requisicion, "REQ-A")

    def test_http_formulario_antiguo_sin_confirmacion_no_factura(self):
        self.client.force_login(self.user)
        r = self.client.post(reverse("facturacion_previsualizar"), {
            "fecha_desde": "2026-10-21", "fecha_hasta": "2026-11-20",
        })
        self.assertEqual(r.status_code, 200)
        self.assertFalse(FacturacionODT.objects.exists())
        self.assertContains(r, "Actualiza la previsualización")

    def test_http_confirmacion_exige_csrf(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.user)
        r = cliente.post(reverse("facturacion_previsualizar"), {
            "fecha_desde": "2026-10-21", "fecha_hasta": "2026-11-20",
        })
        self.assertEqual(r.status_code, 403)
        self.assertFalse(FacturacionODT.objects.exists())

    def test_cambio_de_aprobacion_despues_de_previsualizar_no_se_factura(self):
        vista = previsualizar(self.user, self.seleccion)
        Revision.objects.create(odt=ODT.objects.get(numero=1), estado="RECHAZADA")
        with self.assertRaises(FacturacionInvalida):
            self.confirmar(vista)
        self.assertFalse(FacturacionODT.objects.exists())

    def test_http_editar_requisicion_conserva_redireccion(self):
        self.confirmar()
        self.client.force_login(self.user)
        factura = FacturacionContratista.objects.first()
        r = self.client.post(reverse("actualizar_requisicion", args=[factura.pk]), {"numero_requisicion": "ACTUALIZADA"})
        self.assertEqual(r.status_code, 302)
        self.assertIn(f"periodo={factura.periodo_id}", r.url)
        factura.refresh_from_db()
        self.assertEqual(factura.numero_requisicion, "ACTUALIZADA")
