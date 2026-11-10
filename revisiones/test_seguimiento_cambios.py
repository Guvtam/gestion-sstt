from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase
from django.urls import reverse

from .models import ODT, CorreccionODT
from .vistas.correcciones import odt_modificadas


class SeguimientoCambiosTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser("admin", password="prueba")
        for n in range(1, 6):
            ODT.objects.create(numero=n, contratista="Proveedor", cuenta_completa=f"FIR-{n}",
                               servicio="Original", valor_pago_tecnico=100)
        ODT.objects.filter(numero=1).update(valor_pago_editado=0)
        CorreccionODT.objects.create(odt=ODT.objects.get(numero=2), estado="PENDIENTE",
                                    corrige_monto=True, monto_objetivo=500)
        CorreccionODT.objects.create(odt=ODT.objects.get(numero=3), estado="EN_PROCESO",
                                    corrige_servicio=True, servicio_objetivo="Solicitado", monto_objetivo=100)
        ODT.objects.filter(numero=4).update(valor_pago_tecnico=700)
        CorreccionODT.objects.create(odt=ODT.objects.get(numero=4), estado="ACTUALIZADA",
                                    corrige_monto=True, monto_objetivo=700)

    @staticmethod
    def responsables(request, numeros):
        return {n:{"nombre":"Responsable", "usuario":"jtapia", "identificado":True} for n in numeros}

    def consultar(self, **filtros):
        request = RequestFactory().get("/odt-modificadas/", filtros)
        request.user = self.user
        with patch("revisiones.vistas.correcciones.coordinadores_para_mostrar", side_effect=self.responsables), \
             patch("revisiones.vistas.correcciones.render", side_effect=lambda r,t,c:c):
            return odt_modificadas(request)

    def test_todos_estados_y_legacy_pendiente_priorizados(self):
        contexto = self.consultar()
        self.assertEqual([r["numero"] for r in contexto["filas"]], [2,1,3,4])
        self.assertEqual([t["cantidad"] for t in contexto["tarjetas_estados"]], [4,2,1,1])
        self.assertEqual(contexto["cantidad"], 4)
        self.assertEqual(contexto["monto_original"], Decimal("1000"))
        self.assertEqual(contexto["monto_corregido"], Decimal("1300"))

    def test_filtro_pendiente_incluye_ediciones_sin_seguimiento_y_tarjetas_conservan_otros_estados(self):
        contexto = self.consultar(correccion="PENDIENTE")
        self.assertEqual([r["numero"] for r in contexto["filas"]], [2,1])
        self.assertEqual([t["cantidad"] for t in contexto["tarjetas_estados"]], [4,2,1,1])
        self.assertEqual(contexto["monto_corregido"], Decimal("500"))

    def test_actualizadas_siguen_visibles_y_tipo_usa_objetivo_persistente(self):
        contexto = self.consultar(correccion="ACTUALIZADA", tipo="MONTO")
        self.assertEqual([r["numero"] for r in contexto["filas"]], [4])
        self.assertTrue(contexto["filas"][0]["cambio_monto"])
        self.assertEqual(contexto["filas"][0]["monto_actual"], Decimal("700"))
        self.assertEqual([r["numero"] for r in self.consultar(tipo="SERVICIO")["filas"]], [3])
        self.assertEqual(self.consultar(tipo="AMBOS")["cantidad"], 0)

    def test_busqueda_coordinador_y_enlaces_conservan_filtros(self):
        from urllib.parse import parse_qs, urlsplit
        contexto = self.consultar(q="FIR-2", tipo="MONTO", page="2")
        self.assertEqual([r["numero"] for r in contexto["filas"]], [2])
        parametros = parse_qs(urlsplit(contexto["tarjetas_estados"][2]["url"]).query)
        self.assertEqual(parametros["q"], ["FIR-2"])
        self.assertNotIn("page", parametros)
        with patch("revisiones.vistas.correcciones.coordinadores_en_peticion", return_value={
            1:{"identificado":True,"usuario":"rsilva"}, 2:{"identificado":True,"usuario":"jtapia"},
            3:{"identificado":False},4:{"identificado":True,"usuario":"jtapia"}}):
            self.assertEqual(self.consultar(coordinador="rsilva")["cantidad"],1)

    def test_pagina_real_historial_compartido_y_datos_comparados(self):
        self.client.force_login(self.user)
        with patch("revisiones.vistas.correcciones.coordinadores_para_mostrar", side_effect=self.responsables):
            respuesta = self.client.get(reverse("odt_modificadas"))
        self.assertContains(respuesta, "Seguimiento de cambios de ODT")
        self.assertContains(respuesta, "Servicio solicitado")
        self.assertContains(respuesta, "Ver en bandeja")
        self.assertContains(respuesta, "numero_odt=2")
        self.assertContains(respuesta, "$500")
        self.assertContains(respuesta, 'id="modalHistorial"', count=1)
        self.assertContains(respuesta, "historial_facturacion_odt.js")
        self.assertContains(respuesta, 'aria-label="Paginación superior de cambios"')
        self.assertContains(respuesta, 'aria-label="Paginación inferior de cambios"')

    def test_vacio_y_permiso_requerido_y_coordinador_permanece_restringido(self):
        self.assertEqual(self.consultar(q="no-existe")["cantidad"],0)
        self.user = User.objects.create_user("sin_permisos")
        with self.assertRaises(PermissionDenied):
            self.consultar()
        coordinador = User.objects.create_user("rsilva")
        self.client.force_login(coordinador)
        self.assertRedirects(self.client.get(reverse("odt_modificadas")), reverse("bandeja"), fetch_redirect_response=False)
