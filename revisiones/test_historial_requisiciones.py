from datetime import date, datetime
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .casos_uso.facturacion import actualizar_requisicion, confirmar, previsualizar
from .dominio.facturacion import SeleccionFacturacion
from .dominio.servicios import SERVICIOS_PRINCIPALES
from .facturacion_models import EventoRequisicion, FacturacionContratista, FacturacionODT, PeriodoFacturacion
from .models import ODT


class HistorialRequisicionesTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_superuser("operador", password="prueba")
        self.periodo = PeriodoFacturacion.objects.create(
            fecha_desde=date(2026, 10, 21), fecha_hasta=date(2026, 11, 20))
        self.factura = FacturacionContratista.objects.create(
            periodo=self.periodo, contratista="Contratista de prueba", numero_requisicion="REQ-1")

    def cambiar(self, numero):
        return actualizar_requisicion(self.usuario, facturacion_id=self.factura.pk, numero=numero)

    def test_guarda_valores_actor_y_contexto(self):
        self.cambiar(" REQ-2 ")
        evento = EventoRequisicion.objects.get()
        self.assertEqual((evento.numero_anterior, evento.numero_nuevo), ("REQ-1", "REQ-2"))
        self.assertEqual((evento.usuario, evento.usuario_nombre), (self.usuario, "operador"))
        self.assertEqual(evento.facturacion_identificador, self.factura.pk)
        self.assertEqual(evento.contratista, self.factura.contratista)
        self.assertEqual(evento.fecha_desde, self.periodo.fecha_desde)
        self.assertIsNotNone(evento.fecha)

    def test_sin_cambio_no_duplica_y_vaciar_registra(self):
        self.cambiar("REQ-1")
        self.assertFalse(EventoRequisicion.objects.exists())
        self.cambiar("")
        evento = EventoRequisicion.objects.get()
        self.assertEqual((evento.numero_anterior, evento.numero_nuevo), ("REQ-1", ""))

    def test_fallo_historial_revierte_numero(self):
        with patch("revisiones.casos_uso.facturacion.EventoRequisicion.objects.create",
                   side_effect=RuntimeError("fallo simulado")):
            with self.assertRaises(RuntimeError):
                self.cambiar("REQ-2")
        self.factura.refresh_from_db()
        self.assertEqual(self.factura.numero_requisicion, "REQ-1")
        self.assertFalse(EventoRequisicion.objects.exists())

    def test_sin_permiso_no_cambia_ni_registra(self):
        usuario = User.objects.create_user("sinpermiso")
        with self.assertRaises(PermissionDenied):
            actualizar_requisicion(usuario, facturacion_id=self.factura.pk, numero="REQ-2")
        self.assertFalse(EventoRequisicion.objects.exists())

    def test_sobrevive_eliminacion_de_cabecera_periodo_y_usuario(self):
        self.cambiar("REQ-2")
        identificador = self.factura.pk
        self.factura.delete()
        self.periodo.delete()
        self.usuario.delete()
        evento = EventoRequisicion.objects.get()
        self.assertIsNone(evento.facturacion_id)
        self.assertIsNone(evento.usuario_id)
        self.assertEqual(evento.usuario_nombre, "operador")
        self.assertEqual(evento.facturacion_identificador, identificador)
        self.assertEqual(evento.numero_nuevo, "REQ-2")

    def test_pagina_sin_historia_no_inventa_eventos(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse("historial_requisiciones", args=[self.factura.pk]))
        self.assertContains(respuesta, "No hay cambios registrados")
        self.assertFalse(EventoRequisicion.objects.exists())

    def test_pagina_muestra_historia_escapada(self):
        self.cambiar("<script>alert(1)</script>")
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse("historial_requisiciones", args=[self.factura.pk]))
        self.assertContains(respuesta, "&lt;script&gt;")
        self.assertNotContains(respuesta, "<script>alert(1)</script>")

    def test_pagina_retiene_contexto_tras_eliminar_cabecera(self):
        self.cambiar("REQ-2")
        identificador = self.factura.pk
        self.factura.delete()
        self.client.force_login(self.usuario)
        respuesta = self.client.get(reverse("historial_requisiciones", args=[identificador]))
        self.assertContains(respuesta, "La facturación fue eliminada")
        self.assertContains(respuesta, "Contratista de prueba")
        self.assertContains(respuesta, "REQ-2")

    def test_paginacion_y_orden(self):
        for n in range(51):
            self.cambiar(f"REQ-{n + 2}")
        self.client.force_login(self.usuario)
        url = reverse("historial_requisiciones", args=[self.factura.pk])
        respuesta = self.client.get(url)
        self.assertEqual(len(respuesta.context["pagina"]), 50)
        self.assertEqual(respuesta.context["pagina"][0].numero_nuevo, "REQ-52")
        self.assertEqual(len(self.client.get(url + "?page=2").context["pagina"]), 1)

    def test_acceso_y_metodo(self):
        url = reverse("historial_requisiciones", args=[self.factura.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        usuario = User.objects.create_user("lector")
        self.client.force_login(usuario)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.post(url).status_code, 405)
        self.assertEqual(self.client.get(reverse("historial_requisiciones", args=[9999])).status_code, 404)

    def test_confirmacion_registra_solo_requisiciones_iniciales_no_vacias(self):
        self.factura.delete()
        self.periodo.delete()
        seleccion = SeleccionFacturacion(date(2026, 10, 21), date(2026, 11, 20))
        for n, nombre in ((1, "Con numero"), (2, "Sin numero")):
            ODT.objects.create(numero=n, contratista=nombre, cuenta_completa=f"FIR-{n}",
                servicio=SERVICIOS_PRINCIPALES[0], valor_pago_tecnico=100,
                estado_softguard="Finalizado",
                fecha_finalizacion=timezone.make_aware(datetime(2026, 10, 25, 12)))
        vista = previsualizar(self.usuario, seleccion)
        confirmar(self.usuario, seleccion, requisiciones={"Con numero": "REQ-3", "Sin numero": ""},
                  confirmacion=vista.confirmacion)
        evento = EventoRequisicion.objects.get()
        self.assertEqual((evento.numero_anterior, evento.numero_nuevo), ("", "REQ-3"))
        self.assertEqual(FacturacionODT.objects.count(), 2)

    def test_fallo_historial_revierte_confirmacion_completa(self):
        self.factura.delete()
        self.periodo.delete()
        seleccion = SeleccionFacturacion(date(2026, 10, 21), date(2026, 11, 20))
        ODT.objects.create(numero=1, contratista="Prueba", cuenta_completa="FIR-1",
            servicio=SERVICIOS_PRINCIPALES[0], valor_pago_tecnico=100,
            estado_softguard="Finalizado",
            fecha_finalizacion=timezone.make_aware(datetime(2026, 10, 25, 12)))
        vista = previsualizar(self.usuario, seleccion)
        with patch("revisiones.casos_uso.facturacion.EventoRequisicion.objects.create",
                   side_effect=RuntimeError("fallo simulado")):
            with self.assertRaises(RuntimeError):
                confirmar(self.usuario, seleccion, requisiciones={"Prueba": "REQ"},
                          confirmacion=vista.confirmacion)
        self.assertFalse(PeriodoFacturacion.objects.exists())
        self.assertFalse(FacturacionContratista.objects.exists())
        self.assertFalse(FacturacionODT.objects.exists())
