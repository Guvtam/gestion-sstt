from datetime import date
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch
from django.test import TestCase
from pypdf import PdfReader
from .models import ODT, CatalogoCuenta
from .exportar_pdf import generar_pdf_contratista


class TipoClientePDFTests(TestCase):
    def pdf(self, odts, historico=True):
        registros = [(o, "MANTENIMIENTO PREVENTIVO", Decimal("100"), "Prueba") for o in odts]
        with patch("revisiones.exportar_pdf.consultar_historial_odt", return_value=[]):
            data = generar_pdf_contratista("Prueba", registros, date(2026,9,21), date(2026,10,20), historico=historico)
        return [page.extract_text() for page in PdfReader(BytesIO(data)).pages]

    def test_catalogo_b2b_b2c_en_listado_y_detalle_para_ambos_exportables(self):
        CatalogoCuenta.objects.create(codigo_cuenta="FIR-C193", tipo_cliente="B2B")
        CatalogoCuenta.objects.create(codigo_cuenta="FIR-5429", tipo_cliente="B2C")
        odts = [
            ODT.objects.create(numero=1, cuenta_completa="FIR-C193 - CRUZ VERDE", tipo_cliente="SIN_CLASIFICAR"),
            ODT.objects.create(numero=2, cuenta_completa="fir - 5429 - CUENTA", tipo_cliente="B2B"),
        ]
        for historico in (True, False):
            paginas = self.pdf(odts, historico)
            for tipo in ("B2B", "B2C"):
                self.assertIn(tipo, paginas[0])
                self.assertIn(tipo, "\n".join(paginas[1:]))

    def test_sin_catalogo_o_marcador_automatico_aplica_b2c(self):
        CatalogoCuenta.objects.create(codigo_cuenta="FIR-100", tipo_cliente="SIN_CLASIFICAR")
        odts = [
            ODT.objects.create(numero=1, cuenta_completa="FIR-100 - Cuenta", tipo_cliente="B2B"),
            ODT.objects.create(numero=2, cuenta_completa="FIR-999 - Sin catálogo", tipo_cliente="B2C"),
        ]
        texto = "\n".join(self.pdf(odts))
        self.assertNotIn("B2B", texto)
        self.assertIn("B2C", texto)
        self.assertNotIn("Sin clasificar", texto)

    def test_una_consulta_al_catalogo_por_pdf_y_sin_cambiar_odt(self):
        CatalogoCuenta.objects.create(codigo_cuenta="FIR-100", tipo_cliente="B2B")
        odt = ODT.objects.create(numero=1, cuenta_completa="FIR-100", tipo_cliente="SIN_CLASIFICAR")
        with self.assertNumQueries(1):
            self.pdf([odt])
        odt.refresh_from_db()
        self.assertEqual(odt.tipo_cliente, "SIN_CLASIFICAR")

