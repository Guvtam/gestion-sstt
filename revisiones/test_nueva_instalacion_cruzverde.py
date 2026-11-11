from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader

from .casos_uso.facturacion import previsualizar, confirmar
from .consultas.catalogos_bandeja import servicios_disponibles
from .consultas.indicadores_bandeja import indicadores_financieros
from .consultas.resumen_facturacion import resumir_items
from .dominio.facturacion import SeleccionFacturacion
from .dominio.servicios import SERVICIOS_PRINCIPALES, categoria_servicio
from .facturacion_models import FacturacionODT
from .models import ODT
from .pdf.documento_contratista import construir_documento_contratista

SERVICIO = "MANTENIMIENTO NUEVA INSTALACION CRUZVERDE"


class NuevaInstalacionCruzverdeTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", password="prueba")
        self.client.force_login(self.admin)
        fin = timezone.now() - timedelta(hours=1)
        for numero, servicio in ((1, SERVICIO), (2, "MANTENCION CORRECTIVA CON COBRO")):
            ODT.objects.create(numero=numero, servicio=servicio, valor_pago_tecnico=10000,
                cuenta_completa=f"FIR-{numero} - Cruzverde", contratista="Proveedor", tecnico="Proveedor",
                estado_softguard="Finalizado", fecha_creacion=fin-timedelta(hours=8), fecha_finalizacion=fin)
        ODT.objects.filter(numero=2).update(servicio_editado=SERVICIO, valor_pago_editado=15000)
        parche = patch("revisiones.vistas.bandeja.coordinadores_para_mostrar",
            side_effect=lambda request,numeros:{n:{"nombre":"Responsable","identificado":True} for n in numeros})
        parche.start()
        self.addCleanup(parche.stop)

    def test_catalogo_edicion_y_clasificacion(self):
        self.assertIn(SERVICIO, SERVICIOS_PRINCIPALES)
        self.assertIn(SERVICIO, servicios_disponibles())
        self.assertEqual(categoria_servicio("mantenimiento nueva instalación cruzverde"), "nueva_instalacion_cruzverde")
        self.assertEqual(categoria_servicio("MANTENIMIENTO NUEVA INSTALACION"), "otros")
        r = self.client.post(reverse("guardar_fila"), {"numero":"1", "servicio":SERVICIO, "monto":"12000", "confirmar_monto":"SI"})
        self.assertEqual(r.status_code, 200, r.content)
        odt = ODT.objects.get(numero=1)
        self.assertEqual(odt.valor_pago_tecnico, 10000)
        self.assertEqual(odt.valor_pago_editado, 12000)

    def test_tarjeta_filtro_creacion_y_analisis(self):
        with self.assertNumQueries(1):
            datos = indicadores_financieros(ODT.objects.all())
        self.assertEqual(datos["nueva_instalacion_cruzverde"], {"cantidad":2, "monto":Decimal(25000)})
        for vista in ("bandeja", "bandeja_creacion"):
            r = self.client.get(reverse(vista), {"servicios":SERVICIO, "fecha_desde":"", "fecha_hasta":""})
            self.assertEqual({o.numero for o in r.context["registros"]}, {1,2})
            self.assertContains(r, 'value="'+SERVICIO+'"')
            self.assertEqual(r.context["nueva_instalacion_cruzverde"]["monto"], 25000)
        analisis = self.client.get(reverse("analisis_odt"))
        self.assertEqual(analisis.context["resumen"]["total"], 2)
        self.assertIn(SERVICIO, analisis.context["servicios_seleccionados"])

    def test_facturacion_snapshot_tarjeta_y_pdf(self):
        ODT.objects.all().update(fecha_finalizacion=timezone.make_aware(datetime(2026,11,5,12)))
        seleccion = SeleccionFacturacion(date(2026,10,21), date(2026,11,20), servicios=(SERVICIO,))
        previa = previsualizar(self.admin, seleccion)
        self.assertEqual(previa.cantidad, 2)
        confirmar(self.admin, seleccion, requisiciones={"Proveedor":"REQ-CV"}, confirmacion=previa.confirmacion)
        items = list(FacturacionODT.objects.select_related("odt"))
        resumen = resumir_items(items)
        self.assertEqual(resumen["categorias"]["nueva_instalacion_cruzverde"]["monto"], 25000)
        self.assertEqual(resumen["categorias"]["otros"]["cantidad"], 0)
        ODT.objects.all().update(servicio="OTRO", servicio_editado=None, valor_pago_tecnico=1, valor_pago_editado=None)
        detalle = self.client.get(reverse("detalle_facturacion", args=[items[0].facturacion_id]))
        self.assertEqual(detalle.context["nueva_instalacion_cruzverde"]["monto"], 25000)
        self.assertContains(detalle, "Mantenimiento nueva instalación Cruzverde")
        registros = [(i.odt, i.servicio_facturado, i.monto_facturado, None) for i in items]
        pdf = construir_documento_contratista("Proveedor", registros, date(2026,10,21), date(2026,11,20),
            catalogo_clientes={}, historiales={1:[],2:[]})
        texto = " ".join(" ".join(p.extract_text().split()) for p in PdfReader(BytesIO(pdf)).pages)
        self.assertIn(SERVICIO, texto)
        self.assertIn("25.000", texto)
