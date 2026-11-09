from datetime import date, datetime, timezone
from unittest.mock import patch

from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from .facturacion_models import FacturacionContratista, FacturacionODT, PeriodoFacturacion
from .models import ODT


class HistorialFacturadasTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_superuser("admin", password="prueba")
        self.client.force_login(self.usuario)
        self.odt = ODT.objects.create(numero=70248, cuenta_completa="FIR-4747 - Cuenta")
        periodo = PeriodoFacturacion.objects.create(fecha_desde=date(2025, 12, 21), fecha_hasta=date(2026, 1, 20))
        self.factura = FacturacionContratista.objects.create(periodo=periodo, contratista="Contratista")
        FacturacionODT.objects.create(facturacion=self.factura, odt=self.odt, monto_facturado=20000,
                                     servicio_facturado="MANTENCION CORRECTIVA SIN COBRO")

    def test_detalle_contiene_boton_url_y_modal_completo_sin_consultar_origen(self):
        with patch("revisiones.vistas.odt.consultar_historial_odt") as consultar:
            respuesta = self.client.get(reverse("detalle_facturacion", args=[self.factura.pk]))
        self.assertEqual(respuesta.status_code, 200)
        for identificador in ("modalHistorial", "historialNumero", "historialContenido", "cerrarHistorial"):
            self.assertContains(respuesta, f'id="{identificador}"', count=1)
        self.assertContains(respuesta, 'class="hist-link btn-historial-odt"', count=1)
        self.assertContains(respuesta, f'data-url="{reverse("historial_odt", args=[70248])}"')
        self.assertContains(respuesta, 'data-numero="70248"')
        self.assertContains(respuesta, "historial_facturacion_odt.js")
        consultar.assert_not_called()

    def test_endpoint_del_boton_devuelve_historial(self):
        with patch("revisiones.vistas.odt.consultar_historial_odt", return_value=[{
            "FechaHora": datetime(2026, 1, 12, tzinfo=timezone.utc), "Accion": "Finalizado",
            "Observacion": "Trabajo terminado", "NombreUsuario": "Técnico",
        }]):
            respuesta = self.client.get(reverse("historial_odt", args=[70248]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["total"], 1)
        self.assertEqual(respuesta.json()["eventos"][0]["observacion"], "Trabajo terminado")

    def test_sin_permiso_historial_no_muestra_boton_y_endpoint_denegado(self):
        usuario = User.objects.create_user("exportador")
        permiso, _ = Permission.objects.get_or_create(content_type=ContentType.objects.get_for_model(ODT),
                                                      codename="exportar_pagos_sstt")
        usuario.user_permissions.add(permiso)
        self.client.force_login(usuario)
        respuesta = self.client.get(reverse("detalle_facturacion", args=[self.factura.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, 'class="hist-link btn-historial-odt"')
        self.assertContains(respuesta, "Sin permiso")
        with patch("revisiones.vistas.odt.consultar_historial_odt") as consultar:
            self.assertEqual(self.client.get(reverse("historial_odt", args=[70248])).status_code, 403)
        consultar.assert_not_called()

    def test_facturacion_vacia_conserva_un_solo_modal(self):
        FacturacionODT.objects.all().delete()
        respuesta = self.client.get(reverse("detalle_facturacion", args=[self.factura.pk]))
        self.assertContains(respuesta, "No hay ODT facturadas.")
        self.assertContains(respuesta, 'id="modalHistorial"', count=1)
