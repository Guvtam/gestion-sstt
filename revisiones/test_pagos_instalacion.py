from datetime import date, datetime
from decimal import Decimal
from io import StringIO
from unittest.mock import patch
from django.contrib.auth.models import User, Group
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.http import QueryDict
from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.utils import timezone
from .models import ODT
from .acceso_instalacion import SERVICIO_INSTALACION, limitar_instalacion
from .casos_uso.edicion_odt import editar_odt, revisar_odt, revisar_odts
from .casos_uso.facturacion import previsualizar, confirmar, actualizar_requisicion
from .casos_uso.informes_asignaciones import actualizar_estado_informe
from .dominio.facturacion import SeleccionFacturacion, FacturacionInvalida
from .facturacion_models import FacturacionODT, FacturacionContratista, PeriodoFacturacion
from .consultas.exportacion_pdf import items_facturados, odts_aprobadas
from .vistas.bandeja import pagos_nueva_instalacion


class PagosInstalacionTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user('mixta',password='prueba')
        self.usuario.groups.add(Group.objects.get_or_create(name='Coordinador')[0])
        call_command('habilitar_pagos_instalacion', usuario='mixta', stdout=StringIO())
        self.usuario = User.objects.get(pk=self.usuario.pk)
        self.admin = User.objects.create_superuser('admin',password='prueba')
        self.fecha=timezone.make_aware(datetime(2026,11,5,12))
        self.crear(1, SERVICIO_INSTALACION, 100)
        self.crear(2, 'MANTENIMIENTO NUEVA INSTALACION CRUZVERDE', 200)
        self.crear(3, 'MANTENCION CORRECTIVA CON COBRO', 300)
        self.crear(4, 'Mantenimiento nueva instalación', 400)
        self.client.force_login(self.usuario)

    def crear(self, numero, servicio, monto):
        return ODT.objects.create(numero=numero,servicio=servicio,valor_pago_tecnico=monto,
            contratista='Contratista',cuenta_completa=f'FIR-{numero}',estado_softguard='Finalizado',
            fecha_finalizacion=self.fecha,fecha_creacion=self.fecha)

    def seleccion(self, **datos):
        return SeleccionFacturacion(date(2026,10,21),date(2026,11,20),**datos)

    def test_comando_aditivo_e_idempotente(self):
        call_command('habilitar_pagos_instalacion',usuario='mixta',stdout=StringIO())
        self.assertEqual(set(self.usuario.groups.values_list('name',flat=True)),
                         {'Coordinador','Pagos nueva instalación'})
        self.assertTrue(self.usuario.has_perm('revisiones.exportar_pagos_sstt'))
        self.assertFalse(self.usuario.has_perm('contratistas.ver_bancos_contratistas_sstt'))
        self.assertFalse(self.usuario.is_staff)

    def test_servicio_exacto_incluye_tilde_y_excluye_cruzverde(self):
        self.assertEqual(set(limitar_instalacion(ODT.objects.all()).values_list('numero',flat=True)), {1,4})

    def test_bandeja_adicional_filtra_opciones_indicadores_y_conserva_url(self):
        request=RequestFactory().get('/pagos-nueva-instalacion/', {'fecha_desde':'2026-10-21','fecha_hasta':'2026-11-20'})
        request.user=self.usuario
        with patch('revisiones.vistas.bandeja.coordinadores_para_mostrar',side_effect=lambda r,ns:{n:{'identificado':False} for n in ns}), \
             patch('revisiones.vistas.bandeja.render',side_effect=lambda r,t,c:c):
            contexto=pagos_nueva_instalacion(request)
        self.assertEqual({o.numero for o in contexto['registros']},{1,4})
        self.assertEqual(contexto['total']['monto'],500)
        self.assertEqual(contexto['montos_disponibles'],['100.00','400.00'])
        self.assertEqual(contexto['servicios'],[SERVICIO_INSTALACION])
        self.assertFalse(contexto['es_coordinador'])
        self.assertEqual(contexto['bandeja_url'],'pagos_instalacion')
        from django.template.loader import render_to_string
        html=render_to_string('revisiones/bandeja.html',contexto,request=request)
        self.assertIn('data-puede-editar="1"',html)
        self.assertIn('name="alcance" value="instalacion"',html)

    def test_bandeja_coordinadora_sigue_vacia_sin_vinculo_y_sin_edicion(self):
        with patch('revisiones.vistas.bandeja.coordinadores_para_mostrar',return_value={}):
            respuesta=self.client.get('/',{'fecha_desde':'2026-10-21','fecha_hasta':'2026-11-20'})
        self.assertEqual(respuesta.status_code,200)
        self.assertEqual(respuesta.context['total']['cantidad'],0)
        self.assertContains(respuesta,'data-puede-editar="0"')
        self.assertContains(respuesta,'Pagos nueva instalación')

    def test_ajax_no_incluye_contratistas_de_otros_servicios(self):
        ODT.objects.filter(numero__in=[2,3]).update(contratista='Otro')
        respuesta=self.client.get(reverse('contratistas_disponibles_ajax'),{'alcance':'instalacion',
            'fecha_desde':'2026-10-21','fecha_hasta':'2026-11-20'})
        self.assertEqual(respuesta.json()['contratistas'],['Contratista'])

    def test_edicion_monto_con_confirmacion_y_auditoria(self):
        editar_odt(self.usuario,numero=1,servicio=SERVICIO_INSTALACION,monto='25000',confirmar_monto=True)
        odt=ODT.objects.get(numero=1)
        self.assertEqual(odt.valor_pago_editado,25000)
        self.assertEqual(odt.eventos_revision.get().usuario,self.usuario)

    def test_no_puede_editar_otro_servicio_ni_sacar_odt_del_alcance(self):
        for numero, servicio in ((2,'MANTENIMIENTO NUEVA INSTALACION CRUZVERDE'),
                                 (3,'MANTENCION CORRECTIVA CON COBRO'), (1,'MANTENCION CORRECTIVA CON COBRO')):
            with self.subTest(numero=numero,servicio=servicio), self.assertRaises(PermissionDenied):
                editar_odt(self.usuario,numero=numero,servicio=servicio,monto='2',confirmar_monto=True)
        self.assertFalse(ODT.objects.exclude(valor_pago_editado=None).exists())

    def test_revision_individual_y_lote_son_acotados_y_atomicos(self):
        revisar_odt(self.usuario,numero=1,estado='EN_REVISION',comentario='Revisar')
        with self.assertRaises(PermissionDenied):
            revisar_odt(self.usuario,numero=2,estado='EN_REVISION',comentario='Revisar')
        with self.assertRaises(PermissionDenied):
            revisar_odts(self.usuario,numeros=[1,3],estado='APROBADA')
        self.assertEqual(ODT.objects.get(numero=1).revision.estado,'EN_REVISION')

    def test_informe_adicional_no_requiere_ser_su_coordinadora(self):
        actualizar_estado_informe(self.usuario,numero=1,estado='NO_APLICA',
                                   resolver_responsable=lambda n:{'identificado':False})
        self.assertEqual(ODT.objects.get(numero=1).estado_informe,'NO_APLICA')
        with self.assertRaises(PermissionDenied):
            actualizar_estado_informe(self.usuario,numero=3,estado='NO_APLICA',
                                       resolver_responsable=lambda n:{'identificado':False})

    def test_previsualizar_y_confirmar_solo_instalacion_aunque_manipule_filtros(self):
        seleccion=self.seleccion()
        self.assertEqual(previsualizar(self.usuario,self.seleccion(servicios=('MANTENCION CORRECTIVA CON COBRO',))).cantidad,0)
        vista=previsualizar(self.usuario,seleccion)
        self.assertEqual(vista.cantidad,2)
        self.assertEqual(vista.resumen[0]['monto'],500)
        confirmar(self.usuario,seleccion,requisiciones={'Contratista':'REQ'},confirmacion=vista.confirmacion)
        self.assertEqual(set(FacturacionODT.objects.values_list('odt__numero',flat=True)),{1,4})
        self.assertEqual(previsualizar(self.admin,seleccion).cantidad,2)
        self.assertEqual(previsualizar(self.usuario,self.seleccion(servicios=('MANTENCION CORRECTIVA CON COBRO',))).cantidad,0)

    def test_cambio_de_servicio_entre_previsualizar_y_confirmar_rechaza(self):
        seleccion=self.seleccion()
        vista=previsualizar(self.usuario,seleccion)
        ODT.objects.filter(numero=1).update(servicio='MANTENCION CORRECTIVA CON COBRO')
        with self.assertRaises(FacturacionInvalida):
            confirmar(self.usuario,seleccion,requisiciones={'Contratista':'REQ'},confirmacion=vista.confirmacion)
        self.assertFalse(FacturacionODT.objects.exists())

    def test_permisos_retirados_invalidan_operacion(self):
        self.usuario.groups.remove(Group.objects.get(name='Pagos nueva instalación'))
        usuario=User.objects.get(pk=self.usuario.pk)
        with self.assertRaises(PermissionDenied):
            previsualizar(usuario,self.seleccion())

    def test_reglas_pago_y_facturas_previas_se_conservan(self):
        revisar_odt(self.usuario,numero=1,estado='EN_REVISION',comentario='Revisar')
        self.assertEqual(previsualizar(self.usuario,self.seleccion()).cantidad,1)
        revisar_odt(self.usuario,numero=4,estado='RECHAZADA',comentario='No procede')
        self.assertEqual(previsualizar(self.usuario,self.seleccion()).cantidad,0)

    def facturar_mezcla(self):
        periodo=PeriodoFacturacion.objects.create(fecha_desde=date(2026,10,21),fecha_hasta=date(2026,11,20))
        factura=FacturacionContratista.objects.create(periodo=periodo,contratista='Contratista',numero_requisicion='MIXTA')
        for n in (1,2):
            odt=ODT.objects.get(numero=n)
            FacturacionODT.objects.create(facturacion=factura,odt=odt,
                servicio_facturado=odt.servicio,monto_facturado=odt.valor_pago_tecnico)
        return periodo,factura

    def test_historial_detalle_y_pdf_filtran_instantanea_no_valor_actual(self):
        periodo,factura=self.facturar_mezcla()
        ODT.objects.filter(numero=1).update(servicio='MANTENCION CORRECTIVA CON COBRO')
        ODT.objects.filter(numero=2).update(servicio=SERVICIO_INSTALACION)
        self.assertEqual([i.odt.numero for i in items_facturados(periodo,usuario=self.usuario)],[1])
        respuesta=self.client.get(reverse('historial_facturacion'))
        self.assertEqual(respuesta.status_code,200)
        self.assertEqual(respuesta.context['periodos'][0].monto_total,100)
        self.assertEqual(respuesta.context['periodos'][0].cantidad_odt,1)
        detalle=self.client.get(reverse('detalle_facturacion',args=[factura.pk]))
        self.assertEqual([i.odt.numero for i in detalle.context['items']],[1])
        with patch('revisiones.vistas.exportacion_pdf.generar_zip_facturacion',return_value=b'zip') as pdf:
            respuesta=self.client.get(reverse('exportar_aprobados_pdf'),{'periodo':periodo.pk})
        self.assertEqual(respuesta.status_code,200)
        self.assertEqual([d[0].numero for d in pdf.call_args.args[0]['Contratista']],[1])
        self.assertFalse(pdf.call_args.kwargs['incluir_bancarios'])

    def test_no_cambia_requisicion_mixta_ni_borra_periodo(self):
        periodo,factura=self.facturar_mezcla()
        with self.assertRaises(PermissionDenied):
            actualizar_requisicion(self.usuario,facturacion_id=factura.pk,numero='OTRA')
        self.assertEqual(self.client.get(reverse('historial_requisiciones',args=[factura.pk])).status_code,403)
        self.usuario.is_staff=True;self.usuario.save()
        self.assertEqual(self.client.post(reverse('eliminar_periodo_facturacion',args=[periodo.pk]),
            {'motivo':'prueba','confirmacion':'ELIMINAR'}).status_code,403)
        self.assertTrue(PeriodoFacturacion.objects.filter(pk=periodo.pk).exists())

    def test_requisicion_exclusiva_si_se_puede_editar(self):
        periodo,factura=self.facturar_mezcla()
        FacturacionODT.objects.filter(odt__numero=2).delete()
        actualizar_requisicion(self.usuario,facturacion_id=factura.pk,numero='NUEVA')
        factura.refresh_from_db()
        self.assertEqual(factura.numero_requisicion,'NUEVA')

    def test_pdf_operativo_solo_servicio_y_monto_efectivo(self):
        odts=odts_aprobadas('Contratista',date(2026,10,21),date(2026,11,20),usuario=self.usuario)
        self.assertEqual({o.numero for o in odts},{1,4})

    def test_endpoints_manipulados_no_autorizan_otras_odt(self):
        self.assertEqual(self.client.post(reverse('actualizar_revision'),{'numero':2,'estado':'APROBADA'}).status_code,403)
        self.assertEqual(self.client.post(reverse('guardar_fila'),{'numero':2,'servicio':SERVICIO_INSTALACION,
            'monto':'2','confirmar_monto':'SI'}).status_code,403)

    def test_coordinador_sin_acceso_adicional_no_entra_a_pagos(self):
        usuario=User.objects.create_user('coordinador_normal')
        usuario.groups.add(Group.objects.get(name='Coordinador'))
        self.client.force_login(usuario)
        self.assertNotEqual(self.client.get(reverse('pagos_instalacion')).status_code,200)

    def test_informe_y_procesado_de_sus_otras_odt_se_conservan(self):
        from .casos_uso.gestion_correcciones import gestionar_correccion
        from .models import CorreccionODT
        with patch('revisiones.casos_uso.autorizacion.datos_coordinador',return_value={'usuario':'mixta'}):
            actualizar_estado_informe(self.usuario,numero=3,estado='NO_APLICA',
                resolver_responsable=lambda n:{'identificado':True,'usuario':'mixta'})
        ODT.objects.filter(numero=3).update(valor_pago_tecnico=0)
        CorreccionODT.objects.create(odt=ODT.objects.get(numero=3),estado='PENDIENTE',
            corrige_monto=True,monto_objetivo=2)
        resultado=gestionar_correccion(self.usuario,numero=3,estado='EN_PROCESO',verificar_alcance=lambda n:True)
        self.assertEqual(resultado.estado,'EN_PROCESO')
        with self.assertRaises(PermissionDenied):
            gestionar_correccion(self.usuario,numero=3,estado='EN_PROCESO',verificar_alcance=lambda n:False)

    def test_acceso_directo_historial_e_informe_de_otra_odt_no_consulta_origen(self):
        with patch('revisiones.vistas.odt.consultar_historial_odt') as sql:
            self.assertEqual(self.client.get(reverse('historial_odt',args=[2])).status_code,403)
        sql.assert_not_called()
        self.assertEqual(self.client.post(reverse('actualizar_informe'),{'numero':2,'estado':'NO_APLICA'}).status_code,403)
        self.assertEqual(self.client.post(reverse('actualizar_informe'),{'numero':1,'estado':'NO_APLICA'}).status_code,200)

    def test_http_previsualizacion_y_pdf_respetan_alcance_sin_parametro_especial(self):
        respuesta=self.client.get(reverse('facturacion_previsualizar'),{
            'fecha_desde':'2026-10-21','fecha_hasta':'2026-11-20'})
        self.assertEqual(respuesta.status_code,200)
        self.assertEqual(respuesta.context['cantidad_odt'],2)
        with patch('revisiones.vistas.exportacion_pdf.generar_pdf_contratista',return_value=b'%PDF') as pdf:
            respuesta=self.client.get(reverse('exportar_aprobados_pdf'),{
                'fecha_desde':'2026-10-21','fecha_hasta':'2026-11-20','contratista':'Contratista'})
        self.assertEqual(respuesta.status_code,200)
        self.assertEqual({r[0].numero for r in pdf.call_args.kwargs['registros_contratista']},{1,4})

    def test_bloqueo_facturada_no_se_puede_eludir(self):
        self.facturar_mezcla()
        from .dominio.errores import ODTBloqueada
        with self.assertRaises(ODTBloqueada):
            editar_odt(self.usuario,numero=1,servicio=SERVICIO_INSTALACION,monto=200,confirmar_monto=True)

    def test_filtro_monto_sobre_alcance(self):
        seleccion=self.seleccion(montos=('200.00',),montos_filtrados=True)
        self.assertEqual(previsualizar(self.usuario,seleccion).cantidad,0)
        seleccion=self.seleccion(montos=('100.00',),montos_filtrados=True)
        self.assertEqual(previsualizar(self.usuario,seleccion).cantidad,1)
        self.assertEqual(previsualizar(self.admin,self.seleccion(montos=('200.00',),montos_filtrados=True)).cantidad,1)

    def test_grupo_adicional_sin_grupo_coordinador_no_da_acceso_general(self):
        self.usuario.groups.remove(Group.objects.get(name='Coordinador'))
        self.usuario=User.objects.get(pk=self.usuario.pk)
        from .acceso_coordinadores import es_coordinador_sstt
        self.assertTrue(es_coordinador_sstt(self.usuario))
        self.client.force_login(self.usuario)
        respuesta=self.client.get(reverse('administrar_cuentas'))
        self.assertNotEqual(respuesta.status_code,200)
        with self.assertRaises(PermissionDenied):
            revisar_odt(self.usuario,numero=2,estado='APROBADA')

    def test_guardado_http_positivo_y_auditoria(self):
        respuesta=self.client.post(reverse('guardar_fila'),{'numero':1,'servicio':SERVICIO_INSTALACION,
            'monto':'25000','confirmar_monto':'SI'})
        self.assertEqual(respuesta.status_code,200)
        self.assertEqual(ODT.objects.get(numero=1).valor_pago_editado,25000)
