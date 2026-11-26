"""Requisiciones independientes por contratista/período, sin duplicar ODT."""
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO, StringIO
from unittest.mock import patch
from zipfile import ZipFile
from django.contrib.auth.models import User, Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from .acceso_instalacion import SERVICIO_INSTALACION
from .casos_uso.facturacion import confirmar, previsualizar, actualizar_requisicion
from .dominio.facturacion import SeleccionFacturacion, FacturacionInvalida
from .dominio.servicios import SERVICIOS_PRINCIPALES
from .facturacion_models import FacturacionContratista, FacturacionODT, PeriodoFacturacion, EventoRequisicion
from .models import ODT


class FacturacionMultipleTests(TestCase):
    def setUp(self):
        self.admin=User.objects.create_superuser('admin',password='test')
        self.fecha=timezone.make_aware(datetime(2026,11,5,12))
        self.periodo=PeriodoFacturacion.objects.create(fecha_desde=date(2026,10,21),fecha_hasta=date(2026,11,20))
        self.anterior=FacturacionContratista.objects.create(periodo=self.periodo,contratista='Proveedor A',numero_requisicion='4830')
        for n in (1,2):
            o=self.crear(n,SERVICIO_INSTALACION,125000)
            FacturacionODT.objects.create(facturacion=self.anterior,odt=o,servicio_facturado=SERVICIO_INSTALACION,monto_facturado=125000)
        for n in (3,4,5):self.crear(n,SERVICIOS_PRINCIPALES[0],31500)
        for n in (6,7):self.crear(n,SERVICIOS_PRINCIPALES[2],28000)
        self.seleccion=SeleccionFacturacion(self.periodo.fecha_desde,self.periodo.fecha_hasta,servicios=SERVICIOS_PRINCIPALES)
        self.client.force_login(self.admin)

    def crear(self,numero,servicio,monto,contratista='Proveedor A'):
        return ODT.objects.create(numero=numero,servicio=servicio,contratista=contratista,
            cuenta_completa=f'FIR-{numero}',estado_softguard='Finalizado',fecha_creacion=self.fecha,
            fecha_finalizacion=self.fecha,valor_pago_tecnico=monto)

    def confirmar(self,numero='4832',seleccion=None,usuario=None,vista=None):
        usuario=usuario or self.admin;seleccion=seleccion or self.seleccion
        vista=vista or previsualizar(usuario,seleccion)
        return confirmar(usuario,seleccion,requisiciones={'Proveedor A':numero},confirmacion=vista.confirmacion)

    def test_nueva_requisicion_no_anexa_odt_a_la_anterior(self):
        vista=previsualizar(self.admin,self.seleccion)
        self.assertEqual((vista.cantidad,vista.resumen[0]['monto']),(5,Decimal('150500')))
        self.confirmar(vista=vista)
        self.anterior.refresh_from_db()
        self.assertEqual(self.anterior.numero_requisicion,'4830')
        self.assertEqual(set(self.anterior.items.values_list('odt__numero',flat=True)),{1,2})
        self.assertEqual(sum(self.anterior.items.values_list('monto_facturado',flat=True)),250000)
        nueva=FacturacionContratista.objects.get(numero_requisicion='4832')
        self.assertNotEqual(nueva.pk,self.anterior.pk)
        self.assertEqual(set(nueva.items.values_list('odt__numero',flat=True)),{3,4,5,6,7})
        self.assertEqual(sum(nueva.items.values_list('monto_facturado',flat=True)),150500)
        self.assertEqual(PeriodoFacturacion.objects.count(),1)
        self.assertEqual(FacturacionODT.objects.count(),7)

    def test_previsualizacion_obsoleta_rechaza_sin_tocar_facturacion_anterior(self):
        vista=previsualizar(self.admin,self.seleccion)
        ODT.objects.filter(numero=3).update(valor_pago_editado=2)
        with self.assertRaises(FacturacionInvalida):self.confirmar(vista=vista)
        self.assertEqual(FacturacionContratista.objects.count(),1)
        self.assertEqual(FacturacionODT.objects.count(),2)
        self.assertFalse(EventoRequisicion.objects.exists())

    def test_valores_actuales_no_recalculan_instantanea_anterior(self):
        ODT.objects.filter(numero__in=[1,2]).update(valor_pago_editado=0,servicio_editado='ACTUAL DISTINTO')
        self.assertEqual(previsualizar(self.admin,self.seleccion).cantidad,5)
        self.assertEqual(set(self.anterior.items.values_list('servicio_facturado',flat=True)),{SERVICIO_INSTALACION})
        self.assertEqual(sum(self.anterior.items.values_list('monto_facturado',flat=True)),250000)

    def test_numero_anterior_no_se_reutiliza_y_no_deja_escrituras_parciales(self):
        with self.assertRaises(FacturacionInvalida):self.confirmar(' 4830 ')
        self.assertEqual(FacturacionContratista.objects.count(),1)
        self.assertEqual(FacturacionODT.objects.count(),2)
        self.assertFalse(EventoRequisicion.objects.exists())

    def test_numeros_pendientes_permiten_varias_facturaciones_independientes(self):
        self.confirmar('')
        nueva=self.crear(8,SERVICIOS_PRINCIPALES[0],0)
        self.confirmar('')
        pendientes=list(FacturacionContratista.objects.filter(numero_requisicion='').order_by('pk'))
        self.assertEqual(len(pendientes),2)
        self.assertEqual(set(pendientes[0].items.values_list('odt__numero',flat=True)),{3,4,5,6,7})
        self.assertEqual(list(pendientes[1].items.values_list('odt__numero',flat=True)),[8])
        with self.assertRaises(FacturacionInvalida):
            actualizar_requisicion(self.admin,facturacion_id=pendientes[1].pk,numero='4830')
        actualizar_requisicion(self.admin,facturacion_id=pendientes[1].pk,numero='4840')
        pendientes[0].refresh_from_db();self.anterior.refresh_from_db()
        self.assertEqual(pendientes[0].numero_requisicion,'');self.assertEqual(self.anterior.numero_requisicion,'4830')
        self.assertEqual(EventoRequisicion.objects.get().facturacion_id,pendientes[1].pk)
        self.assertEqual(nueva.item_facturacion.monto_facturado,0)

    def test_repetir_confirmacion_y_unicidad_odt_no_duplican(self):
        from django.db import transaction, IntegrityError
        vista=previsualizar(self.admin,self.seleccion)
        self.confirmar(vista=vista)
        with self.assertRaises(FacturacionInvalida):self.confirmar(vista=vista)
        with self.assertRaises(IntegrityError),transaction.atomic():
            FacturacionODT.objects.create(facturacion=self.anterior,odt=ODT.objects.get(numero=3),
                servicio_facturado='DUPLICADO',monto_facturado=0)
        self.assertEqual(FacturacionContratista.objects.count(),2)
        self.assertEqual(FacturacionODT.objects.count(),7)

    def test_bd_impide_requisicion_repetida_del_mismo_contratista_periodo(self):
        from django.db import transaction, IntegrityError
        with self.assertRaises(IntegrityError),transaction.atomic():
            FacturacionContratista.objects.create(periodo=self.periodo,contratista='Proveedor A',numero_requisicion='4830')
        FacturacionContratista.objects.create(periodo=self.periodo,contratista='Proveedor B',numero_requisicion='4830')
        otro=PeriodoFacturacion.objects.create(fecha_desde=date(2026,11,21),fecha_hasta=date(2026,12,20))
        FacturacionContratista.objects.create(periodo=otro,contratista='Proveedor A',numero_requisicion='4830')
        self.assertEqual(FacturacionContratista.objects.count(),3)

    def test_confirmaciones_anteriores_al_cambio_exigen_actualizar_preview(self):
        from django.core import signing
        from .casos_uso.facturacion import SALT
        vista=previsualizar(self.admin,self.seleccion)
        datos=signing.loads(vista.confirmacion,salt=SALT);datos['version']=1
        for salt in ('sstt.confirmar-facturacion.v1',SALT):
            token=signing.dumps(datos,salt=salt,compress=True)
            with self.assertRaises(FacturacionInvalida):
                confirmar(self.admin,self.seleccion,requisiciones={'Proveedor A':'4832'},confirmacion=token)
        self.assertEqual(FacturacionODT.objects.count(),2)
        self.assertEqual(FacturacionContratista.objects.count(),1)

    def test_auditoria_se_asocia_solo_a_la_nueva_cabecera(self):
        self.confirmar()
        nueva=FacturacionContratista.objects.get(numero_requisicion='4832')
        evento=EventoRequisicion.objects.get()
        self.assertEqual((evento.facturacion_id,evento.numero_anterior,evento.numero_nuevo),(nueva.pk,'','4832'))
        actualizar_requisicion(self.admin,facturacion_id=nueva.pk,numero='4840')
        self.assertEqual(nueva.eventos_requisicion.count(),2)
        self.assertFalse(self.anterior.eventos_requisicion.exists())
        self.anterior.refresh_from_db();self.assertEqual(self.anterior.numero_requisicion,'4830')

    def test_fallo_al_crear_items_revierte_solo_la_nueva_facturacion(self):
        from django.db import IntegrityError
        def fallo(items,**kwargs):
            items[0].save()
            raise IntegrityError('fallo simulado')
        with patch('revisiones.casos_uso.facturacion.FacturacionODT.objects.bulk_create',side_effect=fallo):
            with self.assertRaises(FacturacionInvalida):self.confirmar()
        self.assertEqual(FacturacionContratista.objects.count(),1)
        self.assertEqual(FacturacionODT.objects.count(),2)
        self.assertFalse(EventoRequisicion.objects.exists())
        self.assertEqual(self.anterior.items.count(),2)

    def test_montos_cero_dos_y_servicio_editado_se_congelan_solo_en_nueva(self):
        ODT.objects.filter(numero=3).update(valor_pago_editado=0,servicio_editado=SERVICIOS_PRINCIPALES[1])
        ODT.objects.filter(numero=4).update(valor_pago_editado=2)
        self.confirmar()
        item=FacturacionODT.objects.get(odt__numero=3)
        self.assertEqual((item.monto_facturado,item.servicio_facturado),(Decimal(0),SERVICIOS_PRINCIPALES[1]))
        self.assertEqual(FacturacionODT.objects.get(odt__numero=4).monto_facturado,2)
        self.assertEqual(sum(self.anterior.items.values_list('monto_facturado',flat=True)),250000)

    def test_formulario_muestra_input_nuevo_aunque_exista_requisicion(self):
        r=self.client.get(reverse('facturacion_previsualizar'),{'fecha_desde':'2026-10-21','fecha_hasta':'2026-11-20',
            'servicios':list(SERVICIOS_PRINCIPALES)})
        self.assertEqual(r.status_code,200)
        self.assertContains(r,'name="requisicion_0"')
        self.assertContains(r,'Nueva facturación')
        self.assertEqual(r.context['resumen'][0]['facturaciones_anteriores'],1)
        self.assertEqual((r.context['cantidad_odt'],r.context['monto_total']),(5,Decimal('150500')))
        self.assertEqual(FacturacionContratista.objects.count(),1)

    def test_historial_cuenta_un_contratista_y_dos_facturaciones_independientes(self):
        self.confirmar()
        r=self.client.get(reverse('historial_facturacion'),{'periodo':self.periodo.pk})
        self.assertEqual(r.status_code,200)
        p=r.context['periodos'][0]
        self.assertEqual((p.cantidad_contratistas,p.cantidad_odt,p.monto_total),(1,7,Decimal('400500')))
        self.assertEqual([(f.numero_requisicion,f.cantidad_odt,f.monto_total) for f in r.context['facturaciones']],
                         [('4830',2,Decimal('250000')),('4832',5,Decimal('150500'))])
        self.assertContains(r,'Facturaciones del período')
        buscar=self.client.get(reverse('historial_facturacion'),{'buscar_requisicion':'4832'})
        self.assertEqual([f.numero_requisicion for f in buscar.context['resultados_busqueda']],['4832'])
        for f in r.context['facturaciones']:
            detalle=self.client.get(reverse('detalle_facturacion',args=[f.pk]))
            self.assertEqual(detalle.context['cantidad'],2 if f.pk==self.anterior.pk else 5)

    def test_zip_un_pdf_por_requisicion_sin_mezclar_montos_ni_odt(self):
        from pypdf import PdfReader
        self.confirmar()
        ODT.objects.all().update(valor_pago_tecnico=999999,servicio='ACTUAL DIFERENTE')
        with patch('revisiones.casos_uso.exportacion_pdf.consultar_historial_odt',return_value=[]):
            r=self.client.get(reverse('exportar_aprobados_pdf'),{'periodo':self.periodo.pk})
        self.assertEqual(r.status_code,200)
        with ZipFile(BytesIO(r.content)) as archivo:
            nombres=archivo.namelist();self.assertEqual(len(nombres),2);self.assertEqual(len(set(nombres)),2)
            for req,total,otro in [('4830','250.000','150.500'),('4832','150.500','250.000')]:
                nombre=next(n for n in nombres if f'Req_{req}_' in n)
                texto='\n'.join(p.extract_text() for p in PdfReader(BytesIO(archivo.read(nombre))).pages)
                self.assertIn(req,texto);self.assertIn(total,texto);self.assertNotIn(otro,texto)
                self.assertNotIn('999.999',texto);self.assertNotIn('ACTUAL DIFERENTE',texto)

    def test_zip_seleccion_y_reporte_de_periodo_no_duplican(self):
        self.confirmar();nueva=FacturacionContratista.objects.get(numero_requisicion='4832')
        with patch('revisiones.vistas.exportacion_pdf.generar_pdf_contratista',return_value=b'PDF') as generar:
            r=self.client.get(reverse('exportar_aprobados_pdf'),{'periodo':self.periodo.pk,'seleccion':'1','facturacion':[nueva.pk]})
        self.assertEqual(len(ZipFile(BytesIO(r.content)).namelist()),1)
        self.assertEqual(generar.call_args.kwargs['requisicion'],'4832')
        self.assertEqual({d[0].numero for d in generar.call_args.kwargs['registros_contratista']},{3,4,5,6,7})
        from pypdf import PdfReader
        r=self.client.post(reverse('informe_periodos_pdf'),{'seleccion':str(self.periodo.pk)})
        self.assertEqual(r.status_code,200)
        texto='\n'.join(p.extract_text() for p in PdfReader(BytesIO(r.content)).pages)
        self.assertIn('4830',texto);self.assertIn('4832',texto);self.assertIn('400.500',texto)

    def test_yasna_factura_otro_lote_generico_sin_acceder_a_otros_servicios(self):
        from django.core.exceptions import PermissionDenied
        usuario=User.objects.create_user('mixta');usuario.groups.add(Group.objects.get_or_create(name='Coordinador')[0])
        call_command('habilitar_pagos_instalacion',usuario='mixta',stdout=StringIO())
        self.crear(8,SERVICIO_INSTALACION,500)
        seleccion=SeleccionFacturacion(self.periodo.fecha_desde,self.periodo.fecha_hasta,servicios=(SERVICIO_INSTALACION,))
        self.confirmar('4900',seleccion=seleccion,usuario=usuario)
        self.confirmar('4832')
        generica=FacturacionContratista.objects.get(numero_requisicion='4900')
        otra=FacturacionContratista.objects.get(numero_requisicion='4832')
        self.client.force_login(usuario)
        r=self.client.get(reverse('historial_facturacion'),{'periodo':self.periodo.pk})
        self.assertEqual({f.numero_requisicion for f in r.context['facturaciones']},{'4830','4900'})
        self.assertEqual(r.context['periodos'][0].cantidad_contratistas,1)
        self.assertEqual(r.context['periodos'][0].monto_total,Decimal('250500'))
        actualizar_requisicion(usuario,facturacion_id=generica.pk,numero='4901')
        with self.assertRaises(PermissionDenied):actualizar_requisicion(usuario,facturacion_id=otra.pk,numero='NO')
        with patch('revisiones.vistas.exportacion_pdf.generar_pdf_contratista') as generar:
            r=self.client.get(reverse('exportar_aprobados_pdf'),{'periodo':self.periodo.pk,'seleccion':'1','facturacion':[generica.pk,otra.pk]})
        self.assertEqual(r.status_code,400);generar.assert_not_called()
        self.assertEqual(self.anterior.items.count(),2)

    def test_dos_previsualizaciones_de_servicios_distintos_pueden_confirmarse(self):
        a=SeleccionFacturacion(self.periodo.fecha_desde,self.periodo.fecha_hasta,servicios=(SERVICIOS_PRINCIPALES[0],))
        b=SeleccionFacturacion(self.periodo.fecha_desde,self.periodo.fecha_hasta,servicios=(SERVICIOS_PRINCIPALES[2],))
        va=previsualizar(self.admin,a);vb=previsualizar(self.admin,b)
        self.confirmar('4832',seleccion=a,vista=va)
        self.confirmar('4833',seleccion=b,vista=vb)
        self.assertEqual(FacturacionContratista.objects.count(),3)
        self.assertEqual(FacturacionODT.objects.count(),7)
        self.assertEqual(FacturacionContratista.objects.get(numero_requisicion='4832').items.count(),3)
        self.assertEqual(FacturacionContratista.objects.get(numero_requisicion='4833').items.count(),2)
        self.assertEqual(self.anterior.items.count(),2)

    def test_confirmacion_http_registra_nueva_requisicion_sin_reutilizar_anterior(self):
        url=reverse('facturacion_previsualizar')
        parametros={'fecha_desde':'2026-10-21','fecha_hasta':'2026-11-20','servicios':list(SERVICIOS_PRINCIPALES)}
        r=self.client.get(url,parametros)
        self.assertNotContains(r,'value="4830"')
        datos={**parametros,'confirmacion_facturacion':r.context['confirmacion_facturacion'],'requisicion_0':'4832'}
        r=self.client.post(url,datos)
        self.assertEqual(r.status_code,302)
        nueva=FacturacionContratista.objects.get(numero_requisicion='4832')
        self.assertEqual(nueva.items.count(),5)
        self.assertEqual(self.anterior.items.count(),2)


from django.test import TransactionTestCase
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


class MigracionRequisicionesMultiplesTests(TransactionTestCase):
    def test_migracion_conserva_identificadores_items_instantaneas_y_auditoria(self):
        anterior=[('revisiones','0016_cambios_softguard')]
        nueva=[('revisiones','0017_requisiciones_multiples')]
        executor=MigrationExecutor(connection)
        try:
            executor.migrate(anterior)
            apps=executor.loader.project_state(anterior).apps
            Periodo=apps.get_model('revisiones','PeriodoFacturacion')
            Factura=apps.get_model('revisiones','FacturacionContratista')
            Odt=apps.get_model('revisiones','ODT');Item=apps.get_model('revisiones','FacturacionODT')
            Evento=apps.get_model('revisiones','EventoRequisicion')
            periodo=Periodo.objects.create(fecha_desde=date(2026,10,21),fecha_hasta=date(2026,11,20))
            factura=Factura.objects.create(periodo=periodo,contratista='Proveedor',numero_requisicion='4830')
            odt=Odt.objects.create(numero=99999,valor_pago_editado=0)
            item=Item.objects.create(facturacion=factura,odt=odt,servicio_facturado='HISTORICO',monto_facturado=Decimal('250000.50'))
            evento=Evento.objects.create(facturacion=factura,facturacion_identificador=factura.pk,contratista='Proveedor',
                fecha_desde=periodo.fecha_desde,fecha_hasta=periodo.fecha_hasta,numero_anterior='',numero_nuevo='4830',usuario_nombre='Operador')
            executor=MigrationExecutor(connection);executor.migrate(nueva)
            apps=executor.loader.project_state(nueva).apps
            conservada=apps.get_model('revisiones','FacturacionContratista').objects.get(pk=factura.pk)
            self.assertEqual((conservada.numero_requisicion,conservada.periodo_id),('4830',periodo.pk))
            detalle=apps.get_model('revisiones','FacturacionODT').objects.get(pk=item.pk)
            self.assertEqual((detalle.facturacion_id,detalle.odt_id,detalle.monto_facturado,detalle.servicio_facturado),
                (factura.pk,odt.pk,Decimal('250000.50'),'HISTORICO'))
            audit=apps.get_model('revisiones','EventoRequisicion').objects.get(pk=evento.pk)
            self.assertEqual((audit.facturacion_id,audit.numero_nuevo,audit.usuario_nombre),(factura.pk,'4830','Operador'))
            otra=apps.get_model('revisiones','FacturacionContratista').objects.create(
                periodo_id=periodo.pk,contratista='Proveedor',numero_requisicion='4832')
            self.assertNotEqual(otra.pk,factura.pk)
            self.assertEqual(apps.get_model('revisiones','ODT').objects.get(pk=odt.pk).valor_pago_editado,0)
        finally:
            executor=MigrationExecutor(connection);executor.migrate(executor.loader.graph.leaf_nodes())
