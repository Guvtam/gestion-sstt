from datetime import date
from decimal import Decimal
from io import StringIO
from unittest.mock import patch
from django.core.management import call_command
from django.test import TestCase
from .models import ODT, CatalogoCuenta
from .facturacion_models import PeriodoFacturacion, FacturacionContratista, FacturacionODT
from .cuentas_utils import cargar_catalogo_cuentas, tipo_cliente_cuenta
from .historial_facturacion import resumen_costos_periodo
from .facturacion import resumen_costos_periodo as resumen_alternativo


class ClasificacionConsistenteTests(TestCase):
    def setUp(self):
        CatalogoCuenta.objects.create(codigo_cuenta="FIR-100", tipo_cliente="B2B")
        CatalogoCuenta.objects.create(codigo_cuenta="FIR-200", tipo_cliente="B2C")

    def test_periodos_nuevos_con_odt_desactualizadas_usan_catalogo(self):
        for mes in (8, 9):
            periodo = PeriodoFacturacion.objects.create(fecha_desde=date(2026,mes,21), fecha_hasta=date(2026,mes+1,20))
            factura = FacturacionContratista.objects.create(periodo=periodo, contratista="Prueba", numero_requisicion="REQ")
            for n, codigo, monto in ((1, "100", 100), (2, "200", 200), (3, "999", 50)):
                odt = ODT.objects.create(numero=mes*100+n, cuenta_completa=f"FIR-{codigo} - Cuenta", tipo_cliente="SIN_CLASIFICAR")
                FacturacionODT.objects.create(facturacion=factura, odt=odt, monto_facturado=monto, servicio_facturado="MANTENIMIENTO PREVENTIVO")
            resumen = resumen_costos_periodo(periodo)
            self.assertEqual(resumen["clientes"]["B2B"]["monto"], Decimal("100"))
            self.assertEqual(resumen["clientes"]["B2C"]["monto"], Decimal("250"))
            self.assertEqual(resumen["clientes"]["SIN_CLASIFICAR"]["monto"], Decimal("0"))
            self.assertEqual(sum(v["monto"] for v in resumen["clientes"].values()), resumen["total"])
            self.assertEqual(sum(v["cantidad"] for v in resumen["clientes"].values()), resumen["cantidad"])
            self.assertEqual(resumen_alternativo(periodo)["clientes"]["B2B"], Decimal("100"))

    def test_normalizacion_y_fuente_unica_sin_inferencias(self):
        catalogo = cargar_catalogo_cuentas(["fir - 100 - Cuenta", "FIR-200", "FIR-999"])
        self.assertEqual(tipo_cliente_cuenta("fir - 100 - Cuenta", catalogo), "B2B")
        self.assertEqual(tipo_cliente_cuenta("FIR-200 - Cuenta", catalogo), "B2C")
        self.assertEqual(tipo_cliente_cuenta("FIR-999", catalogo), "B2C")

    def test_consultas_en_lotes(self):
        cuentas = [f"FIR-{n}" for n in range(501)]
        with self.assertNumQueries(2):
            cargar_catalogo_cuentas(cuentas)

    def test_sincronizacion_proyecta_tipo_cliente_para_odt_nueva(self):
        from collections import defaultdict
        registro = defaultdict(lambda: None, {
            "Numero": 90001, "CuentaCompleta": "FIR-100 - Cuenta",
            "Tecnico": "Prueba", "Servicio": "MANTENIMIENTO PREVENTIVO",
        })
        with patch("revisiones.management.commands.sincronizar_odts.consultar_odts_completas", return_value=[registro]):
            call_command("sincronizar_odts", stdout=StringIO())
        self.assertEqual(ODT.objects.get(numero=90001).tipo_cliente, "B2B")

    def test_codigo_invalido_se_mantiene_sin_clasificar(self):
        for valor in ("", None, "Sin cuenta"):
            self.assertEqual(tipo_cliente_cuenta(valor, {}), "SIN_CLASIFICAR")

    def test_marcador_automatico_sin_tipo_es_b2c(self):
        cuenta = CatalogoCuenta.objects.create(codigo_cuenta="FIR-300", tipo_cliente="SIN_CLASIFICAR")
        self.assertEqual(tipo_cliente_cuenta("FIR-300", {"FIR-300": cuenta}), "B2C")

    def test_sincronizacion_b2c_es_estable_y_recalculo_idempotente(self):
        from collections import defaultdict
        registro = defaultdict(lambda: None, {"Numero": 90100, "CuentaCompleta": "FIR-999 - Cuenta"})
        with patch("revisiones.management.commands.sincronizar_odts.consultar_odts_completas", return_value=[registro]):
            for _ in range(2):
                call_command("sincronizar_odts", stdout=StringIO())
                self.assertEqual(ODT.objects.get(numero=90100).tipo_cliente, "B2C")
        odt = ODT.objects.get(numero=90100)
        odt.tipo_cliente = "SIN_CLASIFICAR"
        odt.save()
        call_command("actualizar_tipo_cliente_odts", simular=True, stdout=StringIO())
        odt.refresh_from_db()
        self.assertEqual(odt.tipo_cliente, "SIN_CLASIFICAR")
        for _ in range(2):
            call_command("actualizar_tipo_cliente_odts", stdout=StringIO())
        odt.refresh_from_db()
        self.assertEqual(odt.tipo_cliente, "B2C")
