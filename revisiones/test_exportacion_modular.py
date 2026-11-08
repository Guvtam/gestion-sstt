from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zipfile import ZipFile

from django.test import SimpleTestCase, RequestFactory
from pypdf import PdfReader

from .casos_uso.exportacion_pdf import generar_pdf_contratista, generar_zip_facturacion
from .models import ODT
from .pdf.documento_contratista import construir_documento_contratista
from .pdf.imagenes import descargar_imagen_pdf, SinRedireccion
from .vistas.exportacion_pdf import exportar_aprobados_pdf


class ExportacionModularTests(SimpleTestCase):
    """Django prohíbe consultas ORM en esta clase: el documento usa datos precargados."""
    def setUp(self):
        self.desde=date(2026,10,21)
        self.hasta=date(2026,11,20)
        self.odt=ODT(numero=1,cuenta_completa="FIR-1 - Cuenta",localidad="Localidad",
                     fecha_finalizacion=datetime(2026,11,1,12),observaciones_insumos="Detalle")
        self.filas=[(self.odt,"Servicio facturado",Decimal("0"),"Contratista")]
        self.catalogo={"FIR-1":SimpleNamespace(tipo_cliente="B2B",ceco="50-01-01")}
        self.historiales={1:[{"FechaHora":datetime(2026,11,1,13),"Accion":"FINALIZAR",
                            "NombreUsuario":"Responsable","Observacion":"Trabajo finalizado"}]}

    def construir(self,**opciones):
        return construir_documento_contratista("Contratista",self.filas,self.desde,self.hasta,
                catalogo_clientes=self.catalogo,historiales=self.historiales,**opciones)

    def test_documento_precargado_conserva_listado_y_acciones_sin_orm(self):
        data=self.construir(historico=True)
        pdf=PdfReader(BytesIO(data))
        self.assertGreaterEqual(len(pdf.pages),2)
        texto="\n".join(p.extract_text() for p in pdf.pages)
        for esperado in ("Servicio facturado","50-01-01","B2B","Trabajo finalizado","FINALIZAR"):
            self.assertIn(esperado,texto)
        self.assertLess(pdf.pages[0].extract_text().index("Tipo cliente"),
                        pdf.pages[0].extract_text().index("CECO"))

    def test_historial_ausente_no_se_convierte_en_reporte_completo(self):
        with self.assertRaises(KeyError):
            construir_documento_contratista("Prueba",self.filas,self.desde,self.hasta,
                catalogo_clientes={},historiales={})

    def test_fallo_al_leer_historial_no_construye_documento(self):
        with patch("revisiones.casos_uso.exportacion_pdf.cargar_catalogo_cuentas",return_value={}), \
             patch("revisiones.casos_uso.exportacion_pdf.consultar_historial_odt",side_effect=RuntimeError), \
             patch("revisiones.casos_uso.exportacion_pdf.construir_documento_contratista") as construir:
            with self.assertRaises(RuntimeError):
                generar_pdf_contratista("Prueba",self.filas,self.desde,self.hasta)
        construir.assert_not_called()

    def test_composicion_no_consulta_historial_de_odt_ajenas_y_deduplica(self):
        with patch("revisiones.casos_uso.exportacion_pdf.cargar_catalogo_cuentas",return_value=self.catalogo), \
             patch("revisiones.casos_uso.exportacion_pdf.consultar_historial_odt",return_value=[]) as origen, \
             patch("revisiones.casos_uso.exportacion_pdf.construir_documento_contratista",return_value=b"PDF") as construir:
            resultado=generar_pdf_contratista("Prueba",self.filas+self.filas,self.desde,self.hasta)
        origen.assert_called_once_with(1)
        self.assertEqual(resultado,b"PDF")
        self.assertEqual(construir.call_args.kwargs["historiales"],{1:[]})
        self.assertEqual(len(construir.call_args.args[1]),2)

    def test_zip_independiente_por_contratista_y_nombres_seguros(self):
        grupos={"../Prueba":self.filas,"?Prueba":self.filas}
        def crear(**datos):
            return construir_documento_contratista(**datos,catalogo_clientes=self.catalogo,
                                                   historiales=self.historiales)
        data=generar_zip_facturacion(grupos,{},self.desde,self.hasta,incluir_bancarios=False,
                                    generar_pdf=crear,resolver_contratista=lambda nombre:None)
        with ZipFile(BytesIO(data)) as archivo:
            nombres=archivo.namelist()
            self.assertEqual(len(nombres),2)
            self.assertNotEqual(nombres[0],nombres[1])
            self.assertTrue(all("/" not in nombre and ".." not in nombre for nombre in nombres))
            for nombre in nombres:
                self.assertGreaterEqual(len(PdfReader(BytesIO(archivo.read(nombre))).pages),2)

    def test_zip_fallido_no_devuelve_resultado_parcial(self):
        generar=Mock(side_effect=[b"PDF",RuntimeError("fallo de ejemplo")])
        with self.assertRaises(RuntimeError):
            generar_zip_facturacion({"A":self.filas,"B":self.filas},{},self.desde,self.hasta,
                incluir_bancarios=False,generar_pdf=generar,resolver_contratista=lambda nombre:None)
        self.assertEqual(generar.call_count,2)

    def test_adaptador_zip_fallido_responde_503_sin_descarga(self):
        request=RequestFactory().get("/",{"periodo":"1"})
        request.user=SimpleNamespace(is_authenticated=True,has_perm=lambda permiso:True,has_perms=lambda permisos:True)
        periodo=SimpleNamespace(fecha_desde=self.desde,fecha_hasta=self.hasta)
        factura=SimpleNamespace(contratista="Prueba",numero_requisicion="REQ")
        item=SimpleNamespace(odt=self.odt,facturacion=factura,servicio_facturado="Servicio",monto_facturado=0)
        with patch("revisiones.vistas.exportacion_pdf.get_object_or_404",return_value=periodo), \
             patch("revisiones.vistas.exportacion_pdf.items_facturados",return_value=[item]), \
             patch("revisiones.vistas.exportacion_pdf.generar_zip_facturacion",side_effect=RuntimeError("fallo")):
            respuesta=exportar_aprobados_pdf(request)
        self.assertEqual(respuesta.status_code,503)
        self.assertNotIn("Content-Disposition",respuesta)

    def test_politica_imagenes_rechaza_http_hosts_ajenos_y_redireccion(self):
        with self.settings(SSTT_IMAGE_HOSTS=["imagenes.example"]):
            with patch("revisiones.pdf.imagenes.build_opener") as opener:
                self.assertIsNone(descargar_imagen_pdf("http://imagenes.example/a.png"))
                self.assertIsNone(descargar_imagen_pdf("https://otro.example/a.png"))
                self.assertIsNone(descargar_imagen_pdf("data:image/png;base64,INVALIDO!"))
            opener.assert_not_called()
        self.assertIsNone(SinRedireccion().redirect_request(None,None,302,"",{},"https://otro.example"))
