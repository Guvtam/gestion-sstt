from datetime import date
from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory
from pypdf import PdfReader
from .models import ODT, CatalogoCuenta
from .facturacion_models import PeriodoFacturacion, FacturacionContratista, FacturacionODT
from .exportar_pdf import exportar_aprobados_pdf, generar_pdf_contratista

class ExportacionSeleccionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser("admin", password="test")
        self.periodo = PeriodoFacturacion.objects.create(fecha_desde=date(2026,9,21), fecha_hasta=date(2026,10,20))
        self.facturas = []
        for n in (1, 2):
            factura = FacturacionContratista.objects.create(periodo=self.periodo, contratista=f"Contratista {n}")
            odt = ODT.objects.create(numero=n, cuenta_completa=f"FIR-{n}")
            FacturacionODT.objects.create(facturacion=factura, odt=odt, monto_facturado=100, servicio_facturado="PREVENTIVO")
            self.facturas.append(factura)

    def descargar(self, datos):
        request = RequestFactory().get("/exportar/", {"periodo": self.periodo.pk, **datos})
        request.user = self.user
        return exportar_aprobados_pdf(request)

    def test_exporta_solo_contratista_seleccionado_con_valores_facturados(self):
        with patch("revisiones.exportar_pdf.generar_pdf_contratista", return_value=b"PDF") as generar:
            respuesta = self.descargar({"seleccion": "1", "facturacion": [self.facturas[1].pk]})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(ZipFile(BytesIO(respuesta.content)).namelist()), 1)
        self.assertEqual(generar.call_args.kwargs["nombre_contratista"], "Contratista 2")
        self.assertEqual(generar.call_args.kwargs["registros_contratista"][0][2], Decimal("100"))

    def test_todos_y_compatibilidad_sin_seleccion(self):
        for datos in ({}, {"seleccion": "1", "facturacion": [f.pk for f in self.facturas]}):
            with patch("revisiones.exportar_pdf.generar_pdf_contratista", return_value=b"PDF") as generar:
                self.assertEqual(self.descargar(datos).status_code, 200)
                self.assertEqual(generar.call_count, 2)

    def test_rechaza_vacio_invalido_y_otro_periodo(self):
        otro = PeriodoFacturacion.objects.create(fecha_desde=date(2026,8,21), fecha_hasta=date(2026,9,20))
        ajeno = FacturacionContratista.objects.create(periodo=otro, contratista="Otro")
        for valores in ([], ["abc"], [ajeno.pk], [self.facturas[0].pk, ajeno.pk]):
            with patch("revisiones.exportar_pdf.generar_pdf_contratista") as generar:
                self.assertEqual(self.descargar({"seleccion":"1", "facturacion": valores}).status_code, 400)
                generar.assert_not_called()

    def test_pdf_ceco_despues_tipo_cliente_en_listado_y_detalle(self):
        CatalogoCuenta.objects.create(codigo_cuenta="FIR-1", tipo_cliente="B2B", ceco="50-30-43")
        odt = ODT.objects.get(numero=1)
        for historico in (True, False):
            with patch("revisiones.exportar_pdf.consultar_historial_odt", return_value=[]):
                data = generar_pdf_contratista("Prueba", [(odt, "PREVENTIVO", Decimal("100"), "Prueba")],
                    self.periodo.fecha_desde, self.periodo.fecha_hasta, historico=historico)
            paginas = PdfReader(BytesIO(data)).pages
            for texto in (paginas[0].extract_text(), "\n".join(p.extract_text() for p in paginas[1:])):
                self.assertIn("50-30-43", texto)
                self.assertLess(texto.index("Tipo cliente"), texto.index("CECO"))
