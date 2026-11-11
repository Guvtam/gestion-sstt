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


COMERCIAL = "MANTENIMIENTO ACUERDO COMERCIAL"
PRESUPUESTO = "MANTENIMIENTO PRESUPUESTO"


class ServiciosComercialPresupuestoTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", password="prueba")
        self.client.force_login(self.admin)
        finalizacion = timezone.now() - timedelta(hours=1)
        for numero, servicio, monto in ((1,COMERCIAL,10000),(2,PRESUPUESTO,20000),
                                       (3,SERVICIOS_PRINCIPALES[0],5000),(4,"OTRO SERVICIO",9000)):
            ODT.objects.create(numero=numero,servicio=servicio,valor_pago_tecnico=monto,
                cuenta_completa=f"FIR-{numero} - Cuenta",contratista="Proveedor",tecnico="Proveedor",
                estado_softguard="Finalizado",fecha_creacion=finalizacion-timedelta(hours=8),fecha_finalizacion=finalizacion)
        ODT.objects.filter(numero=3).update(servicio_editado=COMERCIAL,valor_pago_editado=7000)
        self.coordinadores = patch("revisiones.vistas.bandeja.coordinadores_para_mostrar",
            side_effect=lambda request,numeros:{n:{"nombre":"Responsable","identificado":True} for n in numeros})
        self.coordinadores.start()
        self.addCleanup(self.coordinadores.stop)

    def test_catalogo_y_filtro_siempre_incluyen_ambos_sin_registros(self):
        self.assertEqual(SERVICIOS_PRINCIPALES[-2:], (COMERCIAL,PRESUPUESTO))
        ODT.objects.all().delete()
        self.assertEqual(servicios_disponibles(), sorted(SERVICIOS_PRINCIPALES))
        respuesta = self.client.get(reverse("bandeja"))
        self.assertEqual(respuesta.context["servicios_seleccionados"], list(SERVICIOS_PRINCIPALES))
        self.assertContains(respuesta, 'value="'+COMERCIAL+'"')
        self.assertContains(respuesta, 'value="'+PRESUPUESTO+'"')

    def test_primera_carga_y_filtro_individual_usan_servicio_efectivo(self):
        respuesta = self.client.get(reverse("bandeja"))
        self.assertEqual({o.numero for o in respuesta.context["registros"]}, {1,2,3})
        self.assertEqual(respuesta.context["total"]["cantidad"], 3)
        self.assertEqual(respuesta.context["acuerdo_comercial"], {"cantidad":2,"monto":Decimal(17000)})
        self.assertEqual(respuesta.context["presupuesto"], {"cantidad":1,"monto":Decimal(20000)})
        for servicio, numeros in ((COMERCIAL,{1,3}),(PRESUPUESTO,{2})):
            filtrada = self.client.get(reverse("bandeja"), {"servicios":servicio,"fecha_desde":"","fecha_hasta":""})
            self.assertEqual({o.numero for o in filtrada.context["registros"]}, numeros)
            self.assertEqual(filtrada.context["servicios_seleccionados"], [servicio])

    def test_indicadores_sin_consultas_por_servicio_y_categorias_separadas(self):
        with self.assertNumQueries(1):
            datos = indicadores_financieros(ODT.objects.all())
        self.assertEqual(datos["acuerdo_comercial"]["monto"], 17000)
        self.assertEqual(datos["presupuesto"]["monto"], 20000)
        self.assertEqual(categoria_servicio(COMERCIAL.lower()), "acuerdo_comercial")
        self.assertEqual(categoria_servicio("  mantenimiento presupuesto  "), "presupuesto")
        self.assertEqual(categoria_servicio("OTRO SERVICIO"), "otros")

    def test_edicion_admite_ambos_y_conserva_originales(self):
        for servicio in (COMERCIAL,PRESUPUESTO):
            respuesta = self.client.post(reverse("guardar_fila"), {"numero":"4","servicio":servicio,"monto":"9000"})
            self.assertEqual(respuesta.status_code,200,respuesta.content)
            odt = ODT.objects.get(numero=4)
            self.assertEqual(odt.servicio_editado,servicio)
            self.assertEqual(odt.servicio,"OTRO SERVICIO")

    def test_creacion_y_analisis_admiten_los_nuevos_servicios(self):
        respuesta = self.client.get(reverse("bandeja_creacion"), {"servicios":PRESUPUESTO,"fecha_desde":"","fecha_hasta":"","estado":""})
        self.assertEqual({o.numero for o in respuesta.context["registros"]}, {2})
        analisis = self.client.get(reverse("analisis_odt"))
        self.assertEqual(analisis.context["resumen"]["total"], 3)
        self.assertIn(COMERCIAL, analisis.context["servicios_seleccionados"])
        self.assertIn(PRESUPUESTO, analisis.context["servicios_seleccionados"])

    def test_facturacion_conserva_instantaneas_y_resumen_no_los_clasifica_como_otros(self):
        # Período completo y fechas fijas para confirmar una selección reproducible.
        ODT.objects.all().update(fecha_finalizacion=timezone.make_aware(datetime(2026,11,5,12)))
        seleccion = SeleccionFacturacion(date(2026,10,21),date(2026,11,20),servicios=(COMERCIAL,PRESUPUESTO))
        previa = previsualizar(self.admin,seleccion)
        self.assertEqual(previa.cantidad,3)
        confirmar(self.admin,seleccion,requisiciones={"Proveedor":"REQ-NUEVOS"},confirmacion=previa.confirmacion)
        items = list(FacturacionODT.objects.select_related("odt"))
        resumen = resumir_items(items)
        self.assertEqual(resumen["categorias"]["acuerdo_comercial"]["cantidad"],2)
        self.assertEqual(resumen["categorias"]["presupuesto"]["cantidad"],1)
        self.assertEqual(resumen["categorias"]["otros"]["cantidad"],0)
        self.assertEqual(resumen["total"],37000)
        ODT.objects.all().update(servicio="OTRO",servicio_editado=None,valor_pago_tecnico=1,valor_pago_editado=None)
        self.assertEqual(resumir_items(items)["total"],37000)
        detalle = self.client.get(reverse("detalle_facturacion",args=[items[0].facturacion_id]))
        self.assertContains(detalle,"Mantenimiento acuerdo comercial")
        self.assertContains(detalle,"Mantenimiento presupuesto")
        self.assertEqual(detalle.context["acuerdo_comercial"]["monto"],17000)
        self.assertEqual(detalle.context["presupuesto"]["monto"],20000)

    def test_pdf_incluye_nombres_completos_y_montos(self):
        registros=[(ODT.objects.get(numero=1),COMERCIAL,Decimal(10000),None),
                   (ODT.objects.get(numero=2),PRESUPUESTO,Decimal(20000),None)]
        contenido = construir_documento_contratista("Proveedor",registros,date(2026,10,21),date(2026,11,20),
            catalogo_clientes={},historiales={1:[],2:[]})
        texto=" ".join(" ".join(p.extract_text().split()) for p in PdfReader(BytesIO(contenido)).pages)
        self.assertIn(COMERCIAL,texto)
        self.assertIn(PRESUPUESTO,texto)
        self.assertIn("30.000",texto)
