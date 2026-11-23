from unittest.mock import patch
from django.urls import reverse
from . import test_pagos_instalacion as fixtures
from .models import ODT
from .facturacion_models import FacturacionODT, FacturacionContratista


from django.test import TestCase
class DisenoFacturacionInstalacionTests(TestCase):
    setUp = fixtures.PagosInstalacionTests.setUp
    crear = fixtures.PagosInstalacionTests.crear
    facturar_mezcla = fixtures.PagosInstalacionTests.facturar_mezcla

    def preparar(self):
        periodo,factura=self.facturar_mezcla()
        odt=ODT.objects.get(numero=4)
        FacturacionODT.objects.create(facturacion=factura,odt=odt,
            servicio_facturado=odt.servicio,monto_facturado=odt.valor_pago_tecnico)
        otra=FacturacionContratista.objects.create(periodo=periodo,contratista='Solo Cruzverde',numero_requisicion='OCULTA')
        odt=self.crear(5,'MANTENIMIENTO NUEVA INSTALACION CRUZVERDE',99999)
        FacturacionODT.objects.create(facturacion=otra,odt=odt,servicio_facturado=odt.servicio,monto_facturado=99999)
        return periodo,factura,otra

    def test_misma_plantilla_estilos_y_estructura_en_vacio(self):
        respuesta=self.client.get(reverse('historial_facturacion'))
        self.assertTemplateUsed(respuesta,'revisiones/historial_facturacion.html')
        for texto in ('historial_facturacion.css','class="hist-main"','Buscar ODT o requisición',
                      'Períodos registrados','Todavía no existen períodos'):
            self.assertContains(respuesta,texto)
        self.assertNotContains(respuesta,'class="wrap"')

    def test_periodos_y_contratistas_solo_suman_items_autorizados(self):
        periodo,factura,otra=self.preparar()
        respuesta=self.client.get(reverse('historial_facturacion'),{'periodo':periodo.pk})
        p=respuesta.context['periodos'][0]
        self.assertEqual((p.cantidad_contratistas,p.cantidad_odt,p.monto_total),(1,2,500))
        resumen=respuesta.context['resumen_costos']
        self.assertEqual((resumen['cantidad'],resumen['total']),(2,500))
        facturas=respuesta.context['facturaciones']
        self.assertEqual([(f.pk,f.cantidad_odt,f.monto_total) for f in facturas],[(factura.pk,2,500)])
        self.assertContains(respuesta,'Resumen de costos del período')
        self.assertContains(respuesta,'Exportar PDF seleccionados')
        self.assertContains(respuesta,'Contratistas del período')
        self.assertNotContains(respuesta,'Solo Cruzverde')
        self.assertNotContains(respuesta,'OCULTA')
        self.assertNotContains(respuesta,'hist-form-eliminar')
        self.assertNotContains(respuesta,'class="hist-form-requisicion"')
        self.assertContains(respuesta,'Requisición compartida')
        self.assertContains(respuesta,f'value="{factura.pk}" form="exportarSeleccion"')

    def test_buscar_una_odt_cuenta_todas_las_autorizadas_de_su_factura(self):
        self.preparar()
        respuesta=self.client.get(reverse('historial_facturacion'),{'buscar_odt':'1'})
        resultados=respuesta.context['resultados_busqueda']
        self.assertEqual(resultados.paginator.count,1)
        self.assertEqual(resultados[0].cantidad_odt,2)
        self.assertEqual(resultados[0].monto_total,500)
        self.assertContains(respuesta,reverse('pagos_instalacion')+'?numero_odt=1')
        respuesta=self.client.get(reverse('historial_facturacion'),{'buscar_odt':'2'})
        self.assertEqual(respuesta.context['resultados_busqueda'].paginator.count,0)

    def test_formulario_requisicion_exclusiva_y_ocultar_eliminar_aunque_staff(self):
        periodo,factura=self.facturar_mezcla()
        FacturacionODT.objects.filter(odt__numero=2).delete()
        self.usuario.is_staff=True;self.usuario.save()
        respuesta=self.client.get(reverse('historial_facturacion'),{'periodo':periodo.pk})
        self.assertContains(respuesta,'class="hist-form-requisicion"')
        self.assertNotContains(respuesta,'hist-form-eliminar')
        self.assertContains(respuesta,reverse('historial_requisiciones',args=[factura.pk]))

    def test_no_puede_seleccionar_periodo_o_factura_ajenos(self):
        periodo,factura,otra=self.preparar()
        self.assertEqual(self.client.get(reverse('historial_facturacion'),{
            'periodo':periodo.pk,'contratista':otra.pk}).status_code,404)
        self.assertEqual(self.client.get(reverse('historial_facturacion'),{'periodo':'invalido'}).status_code,404)

    def test_tarjetas_superiores_y_operativas_sin_intermedias(self):
        with patch('revisiones.vistas.bandeja.coordinadores_para_mostrar',
                   side_effect=lambda r,ns:{n:{'identificado':False} for n in ns}):
            respuesta=self.client.get(reverse('pagos_instalacion'),{
                'fecha_desde':'2026-10-21','fecha_hasta':'2026-11-20'})
        self.assertEqual(respuesta.status_code,200)
        for texto in ('ODT filtradas','Aprobados','En revisión','Rechazados',
                      'Total ODT','ODT modificadas','Servicios a corregir','Montos a corregir'):
            self.assertContains(respuesta,texto)
        self.assertNotContains(respuesta,'class="kpis kpis-servicios"')
        self.assertEqual(respuesta.context['total']['cantidad'],2)
        self.assertEqual(respuesta.context['total']['monto'],500)

    def test_supervision_conserva_tarjetas_y_historial_completo(self):
        periodo,factura,otra=self.preparar()
        self.client.force_login(self.admin)
        respuesta=self.client.get(reverse('historial_facturacion'),{'periodo':periodo.pk})
        self.assertEqual(respuesta.context['periodos'][0].cantidad_odt,4)
        self.assertContains(respuesta,'Solo Cruzverde')
        with patch('revisiones.vistas.bandeja.coordinadores_para_mostrar',
                   side_effect=lambda r,ns:{n:{'identificado':False} for n in ns}):
            respuesta=self.client.get('/',{'fecha_desde':'2026-10-21','fecha_hasta':'2026-11-20'})
        self.assertContains(respuesta,'class="kpis kpis-servicios"')
