"""Regresiones de alcance, importes, ventanas y orden global del piloto local."""
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO, StringIO
from unittest.mock import patch
from django.contrib.auth.models import User, Group, Permission
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.http import HttpResponse
from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook
from pypdf import PdfReader
from .models import ODT, Revision, CorreccionODT
from .indicadores_odt import con_indicadores_odt
from .metricas_analisis import cargar_metricas
from .consultas.fallos_prueba import marcar_fallos
from .consultas.filas_bandeja import paginar_filas
from .facturacion_models import PeriodoFacturacion, FacturacionContratista, FacturacionODT
from .vistas.reportes_consulta import exportar_bandeja, ids_seleccion
from .acceso_instalacion import SERVICIO_INSTALACION


def pdf_texto(respuesta):
    return '\n'.join(p.extract_text() for p in PdfReader(BytesIO(respuesta.content)).pages)


def responsables(request, numeros):
    return {n:{'identificado':True,'usuario':'jtapia','nombre':'Josué Tapia'} for n in numeros}


class VentanasYOrdenTests(TestCase):
    def setUp(self):
        self.ahora = timezone.now().replace(microsecond=0)
        self.usuario = User.objects.create_user('jiturriaga')

    def crear(self, numero, dias, **extras):
        datos = dict(cuenta_completa='FIR-1', contratista='Técnico', estado_softguard='Finalizado',
            fecha_finalizacion=self.ahora-timedelta(days=dias),fecha_creacion=self.ahora-timedelta(days=dias,hours=24))
        datos.update(extras)
        return ODT.objects.create(numero=numero,**datos)

    def test_ventanas_acumulativas_13_8_5_y_exclusiones(self):
        for n,dias in enumerate([1,5,10,20,30,31,45,60,61,70,80,89,90],1): self.crear(n,dias)
        self.crear(20,91);self.crear(21,-1);self.crear(22,1,contratista='Otro')
        self.crear(23,1,cuenta_completa='Otra');self.crear(24,1,estado_softguard='Asignado')
        self.crear(25,1,contratista='');self.crear(26,1,cuenta_completa='')
        with patch('revisiones.indicadores_odt.timezone.now',return_value=self.ahora):
            fila=con_indicadores_odt(ODT.objects.filter(numero=1)).get()
            blancos=list(con_indicadores_odt(ODT.objects.filter(numero__in=[25,26])))
        with patch('revisiones.metricas_analisis.timezone.now',return_value=self.ahora):
            rapida=cargar_metricas(ODT.objects.filter(numero=1))[0]
        for o in [fila,rapida]:
            self.assertEqual((o.cantidad_incidencias,o.cantidad_incidencias_60,o.cantidad_incidencias_30),(13,8,5))
            self.assertEqual(o.estado_sla,'CUMPLE')
        for o in blancos:self.assertEqual((o.cantidad_incidencias,o.cantidad_incidencias_60,o.cantidad_incidencias_30),(0,0,0))

    def test_detecta_mayusculas_minusculas_tildes_y_frases_en_texto(self):
        frases=['FDP requerido','fDp','Fallo de prueba en alarma','FALLO DE PRUEBA',
                'Reporta fallo de comunicación','FALLO DE COMUNICACIÓN','fallo de comunicacion',
                'fallo  de\nprueba','Sin anomalías']
        for n,obs in enumerate(frases,1):self.crear(n,1,observaciones_insumos=obs)
        qs,activo=marcar_fallos(ODT.objects.all(),self.usuario)
        self.assertTrue(activo)
        self.assertEqual(set(qs.filter(es_fallo_prueba=True).values_list('numero',flat=True)),set(range(1,9)))
        otro=User.objects.create_user('consulta')
        qs,activo=marcar_fallos(ODT.objects.all(),otro)
        self.assertFalse(activo);self.assertFalse(any(o.es_fallo_prueba for o in qs))

    def test_fallos_al_final_global_antes_de_paginar_incluso_con_correccion(self):
        for n in range(1,56):self.crear(n,1,cuenta_completa='Z - normal')
        for n in range(56,61):self.crear(n,1,cuenta_completa='A - fallo',observaciones_insumos='fdp')
        CorreccionODT.objects.create(odt=ODT.objects.get(numero=56),corrige_monto=True,monto_objetivo=2)
        qs,activo=marcar_fallos(con_indicadores_odt(ODT.objects.all()),self.usuario)
        primera=paginar_filas(qs,1,priorizar_fallos=activo)
        ultima=paginar_filas(qs,2,priorizar_fallos=activo)
        self.assertEqual(len(primera),50)
        self.assertFalse(any(o.es_fallo_prueba for o in primera))
        self.assertEqual([o.es_fallo_prueba for o in ultima],[False]*5+[True]*5)
        self.assertEqual(ultima.object_list[5].numero,56)


class ExportacionesCorporativasTests(TestCase):
    def setUp(self):
        self.admin=User.objects.create_superuser('jiturriaga',password='test')
        self.fecha=timezone.now()-timedelta(days=2)
        self.odt=ODT.objects.create(numero=1001,cuenta_completa='FIR-1001 - Exportación',
            tecnico='T. INTERNO - ServicioStgo',contratista='Contratista',servicio='MANTENCION CORRECTIVA CON COBRO',
            observaciones_insumos='=SUM(A1:A3) texto <no html> & completo',valor_pago_tecnico=1200,
            valor_pago_editado=0,fecha_creacion=self.fecha-timedelta(hours=2),fecha_finalizacion=self.fecha,
            fecha_visita=date(2026,11,10),estado_softguard='Finalizado')
        self.otra=ODT.objects.create(numero=1002,cuenta_completa='AJENA',servicio='MANTENIMIENTO PREVENTIVO',
            contratista='Otro',valor_pago_tecnico=900,valor_pago_editado=2,fecha_finalizacion=self.fecha,estado_softguard='Finalizado')
        self.client.force_login(self.admin)

    def descarga(self, formato='xlsx', seleccion='1001,1002', queryset=None):
        req=RequestFactory().post('/?q=prueba',{'formato':formato,'seleccion':seleccion});req.user=self.admin
        with patch('revisiones.acceso_coordinadores.coordinadores_para_mostrar',side_effect=responsables):
            return exportar_bandeja(req,con_indicadores_odt(queryset if queryset is not None else ODT.objects.all()),coordinador=False)

    def test_excel_importes_cero_dos_logo_columnas_y_texto_sin_formula(self):
        r=self.descarga();self.assertEqual(r.status_code,200)
        ws=load_workbook(BytesIO(r.content)).active
        self.assertEqual(len(ws._images),1)
        headers={c.value:c.column for c in ws[6]}
        filas={ws.cell(n,headers['ODT']).value:n for n in range(7,ws.max_row+1)}
        self.assertEqual(ws.cell(filas[1001],headers['Pago efectivo']).value,0)
        self.assertEqual(ws.cell(filas[1002],headers['Pago efectivo']).value,2)
        obs=ws.cell(filas[1001],headers['Observaciones'])
        self.assertEqual(obs.data_type,'s');self.assertEqual(obs.value,self.odt.observaciones_insumos)
        self.assertEqual(ws.cell(filas[1001],headers['Coordinador']).value,'Josué Tapia')
        self.assertIn('CECO',headers);self.assertIn('Último preventivo',headers)
        self.assertEqual(ODT.objects.get(pk=self.odt.pk).valor_pago_editado,0)
        self.assertFalse(Revision.objects.exists());self.assertFalse(FacturacionODT.objects.exists())

    def test_pdf_escapa_textos_y_total_sin_perder_ajustes(self):
        texto=pdf_texto(self.descarga('pdf'))
        self.assertIn('texto <no html> & completo',texto)
        self.assertIn('$ 2,00',texto);self.assertIn('$ 2.100,00',texto)
        self.assertIn('ÁREA MANTENIMIENTO',texto);self.assertIn('CECO',texto)
        self.assertNotIn('Banco',texto)

    def test_seleccion_fuera_de_filtros_se_rechaza_completa(self):
        r=self.descarga(queryset=ODT.objects.filter(numero=1001))
        self.assertEqual(r.status_code,400)
        self.assertEqual(self.descarga(seleccion='1001,999999').status_code,400)

    def test_validacion_seleccion_y_formato(self):
        for s in ('','-1','1.2','١','1,',','.join(['1']*2001)):
            with self.subTest(s=s[:30]),self.assertRaises(ValueError):ids_seleccion(s)
        self.assertEqual(ids_seleccion('2,1,2'),[1,2])
        self.assertEqual(self.descarga('html').status_code,400)

    def test_exportacion_ruta_real_respeta_filtros_y_seleccion_entre_paginas(self):
        ODT.objects.bulk_create([ODT(numero=n,cuenta_completa=f'FIR-{n}',contratista='Contratista',
            servicio=self.odt.servicio,fecha_finalizacion=self.fecha,estado_softguard='Finalizado') for n in range(1100,1151)])
        url=reverse('bandeja')+'?fecha_desde=2026-01-01&fecha_hasta=2026-12-31&page=2'
        with patch('revisiones.acceso_coordinadores.coordinadores_para_mostrar',side_effect=responsables):
            r=self.client.post(url,{'exportar':'seleccion','seleccion':'1001,1150','formato':'xlsx'})
        self.assertEqual(r.status_code,200)
        ws=load_workbook(BytesIO(r.content)).active
        self.assertEqual({ws.cell(n,1).value for n in range(7,ws.max_row+1)},{1001,1150})
        with patch('revisiones.acceso_coordinadores.coordinadores_para_mostrar',side_effect=responsables):
            r=self.client.post(url+'&q=INEXISTENTE',{'exportar':'seleccion','seleccion':'1001','formato':'pdf'})
        self.assertEqual(r.status_code,400)

    def test_sin_permiso_y_coordinador_no_exportan_pagos(self):
        usuario=User.objects.create_user('lector')
        req=RequestFactory().post('/',{'seleccion':'1001','formato':'pdf'});req.user=usuario
        with self.assertRaises(PermissionDenied):exportar_bandeja(req,ODT.objects.all(),coordinador=False)
        req.user=self.admin
        with self.assertRaises(PermissionDenied):exportar_bandeja(req,ODT.objects.all(),coordinador=True)

    def test_calendario_pdf_internos_mantiene_alcance_y_no_incluye_montos(self):
        call_command('configurar_perfiles',stdout=StringIO())
        usuario=User.objects.create_user('calvarez')
        call_command('habilitar_calendario_internos',usuario='calvarez',stdout=StringIO())
        self.client.force_login(usuario)
        self.otra.fecha_visita=date(2026,11,10);self.otra.tecnico='T. EXTERNO - Secreto';self.otra.save()
        r=self.client.get(reverse('calendario_servicios'),{'mes':'2026-11','formato':'pdf','categoria':'realizadas'})
        self.assertEqual(r.status_code,200)
        t=pdf_texto(r);self.assertIn('FIR-1001',t);self.assertNotIn('AJENA',t);self.assertNotIn('Pago',t)
        self.assertEqual(self.client.post(reverse('informe_periodos_pdf'),{'seleccion':'1'}).status_code,403)

    def test_calendario_pdf_filtro_servicio_y_mes_invalido(self):
        r=self.client.get(reverse('calendario_servicios'),{'mes':'2026-11','formato':'pdf','q':'NINGUNO'})
        self.assertEqual(r.status_code,200);self.assertNotIn('FIR-1001',pdf_texto(r))
        self.assertEqual(self.client.get(reverse('calendario_servicios'),{'mes':'invalid','formato':'pdf'}).status_code,400)

    def facturar(self, odt, mes, servicio, monto):
        p=PeriodoFacturacion.objects.create(fecha_desde=date(2026,mes,21),fecha_hasta=date(2026,mes+1,20))
        f=FacturacionContratista.objects.create(periodo=p,contratista='Contratista histórico',numero_requisicion='REQ-HIST')
        FacturacionODT.objects.create(facturacion=f,odt=odt,servicio_facturado=servicio,monto_facturado=monto)
        return p

    def test_pdf_varios_periodos_usa_instantaneas_y_requisicion(self):
        p=self.facturar(self.odt,9,'SERVICIO HISTORICO',Decimal('123.45'))
        p2=self.facturar(self.otra,10,'SEGUNDO HISTORICO',Decimal('2'))
        ODT.objects.all().update(valor_pago_tecnico=999999,valor_pago_editado=999999,servicio_editado='ACTUAL SECRETO',contratista='ACTUAL DISTINTO')
        r=self.client.post(reverse('informe_periodos_pdf'),{'seleccion':f'{p.pk},{p2.pk}'})
        self.assertEqual(r.status_code,200);t=pdf_texto(r)
        for v in ('SERVICIO HISTORICO','SEGUNDO HISTORICO','REQ-HIST','Contratista histórico','$ 125,45'):self.assertIn(v,t)
        for v in ('ACTUAL SECRETO','999.999','ACTUAL DISTINTO','Banco'):self.assertNotIn(v,t)
        self.assertEqual(FacturacionODT.objects.count(),2)
        self.assertEqual(self.client.get(reverse('informe_periodos_pdf')).status_code,405)

    def test_yasna_pdf_periodos_filtra_por_servicio_facturado_no_actual(self):
        usuario=User.objects.create_user('mixta');usuario.groups.add(Group.objects.get_or_create(name='Coordinador')[0])
        call_command('habilitar_pagos_instalacion',usuario='mixta',stdout=StringIO())
        p=self.facturar(self.odt,9,SERVICIO_INSTALACION,100)
        p2=self.facturar(self.otra,10,'MANTENIMIENTO NUEVA INSTALACION CRUZVERDE',900)
        self.client.force_login(usuario)
        r=self.client.post(reverse('informe_periodos_pdf'),{'seleccion':str(p.pk)})
        self.assertEqual(r.status_code,200);self.assertIn('$ 100,00',pdf_texto(r));self.assertNotIn('AJENA',pdf_texto(r))
        self.assertEqual(self.client.post(reverse('informe_periodos_pdf'),{'seleccion':f'{p.pk},{p2.pk}'}).status_code,403)

    def test_yasna_bandeja_exporta_solo_instalacion_generica(self):
        usuario=User.objects.create_user('mixta');usuario.groups.add(Group.objects.get_or_create(name='Coordinador')[0])
        call_command('habilitar_pagos_instalacion',usuario='mixta',stdout=StringIO())
        self.odt.servicio=SERVICIO_INSTALACION;self.odt.save();self.client.force_login(usuario)
        url=reverse('pagos_instalacion')+'?fecha_desde=2026-01-01&fecha_hasta=2026-12-31'
        with patch('revisiones.acceso_coordinadores.coordinadores_para_mostrar',side_effect=responsables):
            self.assertEqual(self.client.post(url,{'exportar':'seleccion','seleccion':'1001','formato':'pdf'}).status_code,200)
            self.assertEqual(self.client.post(url,{'exportar':'seleccion','seleccion':'1001,1002','formato':'pdf'}).status_code,400)

    def test_analisis_pdf_exporta_todo_el_detalle_y_respeta_filtros(self):
        from .analisis_odt import analisis_odt
        ODT.objects.bulk_create([ODT(numero=n,cuenta_completa='FIR-COMUN',contratista='Contratista',
            servicio=self.odt.servicio,fecha_creacion=self.fecha-timedelta(hours=1),fecha_finalizacion=self.fecha,
            estado_softguard='Finalizado') for n in range(1200,1255)])
        req=RequestFactory().get('/',{'desde':'2026-01-01','hasta':'2026-12-31','q':'FIR-COMUN','formato':'pdf','page':'2'})
        req.user=self.admin
        with patch('revisiones.pdf.reportes.pdf_reporte',return_value=HttpResponse(b'ok')) as pdf:
            r=analisis_odt(req)
        self.assertEqual(r.status_code,200)
        secciones=pdf.call_args.args[1];detalle=next(s[2] for s in secciones if s[0].startswith('Detalle'))
        self.assertEqual(len(detalle),55);self.assertEqual({d[0] for d in detalle},set(range(1200,1255)))
        # Generar realmente el PDF además de comprobar el contenido previo a maquetar.
        req.GET=req.GET.copy();req.GET['q']='FIR-1001';r=analisis_odt(req)
        self.assertEqual(r.status_code,200);self.assertIn('FIR-1001',pdf_texto(r));self.assertNotIn('AJENA',pdf_texto(r))

    def test_coordinadores_pdf_carga_total_y_correcciones_filtradas(self):
        from .estadisticas_correcciones import estadisticas_correcciones
        CorreccionODT.objects.create(odt=self.odt,corrige_monto=True,monto_objetivo=0)
        req=RequestFactory().get('/',{'carga_desde':'2026-01-01','carga_hasta':'2026-12-31','formato':'pdf'})
        req.user=self.admin
        with patch('revisiones.estadisticas_correcciones.coordinadores_en_peticion',side_effect=responsables):
            r=estadisticas_correcciones(req)
        self.assertEqual(r.status_code,200);self.assertIn('Josué Tapia',pdf_texto(r));self.assertIn('FIR-1001',pdf_texto(r))
        with patch('revisiones.estadisticas_correcciones.resumir_carga',return_value={'filas':[],'opciones':{},'disponible':False}), \
             patch('revisiones.estadisticas_correcciones.coordinadores_en_peticion',side_effect=responsables):
            self.assertEqual(estadisticas_correcciones(req).status_code,503)

    def test_marca_en_login_admin_y_bases_operativas(self):
        from django.template.loader import render_to_string
        for nombre in ('revisiones/base_operativa.html','contratistas/base.html'):
            req=RequestFactory().get('/');req.user=self.admin
            html=render_to_string(nombre,{'user':self.admin},request=req)
            self.assertIn('marca/logo_area.png',html)
        self.assertContains(self.client.get(reverse('admin:index')),'marca/logo_area.png')
        self.client.logout();self.assertContains(self.client.get(reverse('login')),'marca/logo_area.png')

    def test_excel_no_trunca_observaciones_extensas(self):
        from .pdf.reportes import xlsx_reporte
        r=xlsx_reporte(['Observaciones'],[['a'*32768]])
        self.assertEqual(r.status_code,400)

    def test_juan_pablo_ve_marca_incidencias_y_no_cambia_montos_al_consultar(self):
        self.odt.observaciones_insumos='FaLLo de comunicación en dispositivo';self.odt.valor_pago_editado=10;self.odt.save()
        with patch('revisiones.vistas.bandeja.coordinadores_para_mostrar',side_effect=responsables):
            r=self.client.get(reverse('bandeja'),{'fecha_desde':'2026-01-01','fecha_hasta':'2026-12-31'})
        self.assertEqual(r.status_code,200)
        self.assertContains(r,'odt-fallo-prueba');self.assertContains(r,'FDP / fallo detectado')
        self.assertContains(r,'90 / 60 / 30 días')
        self.assertEqual(ODT.objects.get(pk=self.odt.pk).valor_pago_editado,10)

    def test_yasna_periodo_mixto_excluye_item_ajeno(self):
        usuario=User.objects.create_user('mixta');usuario.groups.add(Group.objects.get_or_create(name='Coordinador')[0])
        call_command('habilitar_pagos_instalacion',usuario='mixta',stdout=StringIO())
        p=self.facturar(self.odt,9,SERVICIO_INSTALACION,100)
        f=FacturacionContratista.objects.get(periodo=p)
        FacturacionODT.objects.create(facturacion=f,odt=self.otra,servicio_facturado='SERVICIO AJENO',monto_facturado=900)
        self.client.force_login(usuario)
        r=self.client.post(reverse('informe_periodos_pdf'),{'seleccion':str(p.pk)})
        self.assertEqual(r.status_code,200);t=pdf_texto(r)
        self.assertIn('$ 100,00',t);self.assertNotIn('SERVICIO AJENO',t);self.assertNotIn('$ 1.000,00',t)

    def test_descargas_post_exigen_csrf(self):
        from django.test import Client
        c=Client(enforce_csrf_checks=True);c.force_login(self.admin)
        for url in (reverse('bandeja'),reverse('informe_periodos_pdf')):
            self.assertEqual(c.post(url,{'exportar':'seleccion','seleccion':'1001','formato':'pdf'}).status_code,403)
