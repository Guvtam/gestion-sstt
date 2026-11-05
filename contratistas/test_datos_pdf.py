from datetime import date
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch
from django.test import TestCase
from pypdf import PdfReader
from revisiones.models import ODT
from revisiones.exportar_pdf import datos_contratista_pdf, generar_pdf_contratista
from .models import Contratista, EquivalenciaSoftGuard

class DatosPDFTests(TestCase):
    def setUp(self):
        self.c = Contratista.objects.create(nombre="Proveedor prueba", nombre_empresa="Empresa de prueba",
            rut="11111111-1", fono="123456", correo="uno@example.com", correo_alternativo="dos@example.com",
            ciudad="Ciudad Prueba", banco="Banco Prueba", tipo_cuenta="Cuenta corriente",
            numero_cuenta="000123456789", categoria="Factura")
        self.odt = ODT.objects.create(numero=1, cuenta_completa="FIR-100")
        EquivalenciaSoftGuard.objects.create(contratista=self.c, nombre_softguard="T. EXTERNO - Prueba")

    def pdf(self, bancarios=False, datos=True):
        with patch("revisiones.exportar_pdf.consultar_historial_odt", return_value=[]):
            pdf = generar_pdf_contratista("T. EXTERNO - Prueba",
                [(self.odt, "PREVENTIVO", Decimal("100"), "Prueba")],
                date(2026,9,21), date(2026,10,20), historico=True,
                datos_contratista=self.c if datos else None, incluir_bancarios=bancarios)
        return PdfReader(BytesIO(pdf)).pages[0].extract_text()

    def test_resuelve_vinculo_y_no_adivina(self):
        self.assertEqual(datos_contratista_pdf("t. externo - prueba"), self.c)
        self.assertIsNone(datos_contratista_pdf("Nombre parecido"))

    def test_datos_al_comienzo_y_cuenta_con_ceros(self):
        texto = self.pdf(True)
        for valor in ("11111111-1", "123456", "uno@example.com", "dos@example.com", "Ciudad Prueba",
                      "Banco Prueba", "Cuenta corriente", "000123456789", "Factura"):
            self.assertIn(valor, texto)
        self.assertLess(texto.index("Datos del contratista"), texto.index("Listado de ODT"))

    def test_permiso_bancario_restringe_valores(self):
        texto = self.pdf(False)
        self.assertNotIn("Banco Prueba", texto)
        self.assertNotIn("000123456789", texto)
        self.assertIn("Acceso restringido", texto)

    def test_sin_vinculo_no_mezcla_informacion(self):
        texto = self.pdf(datos=False)
        self.assertIn("sin vínculo validado", texto)
        self.assertNotIn("11111111-1", texto)
