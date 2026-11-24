from datetime import date
from io import StringIO
from unittest.mock import patch
from django.contrib.auth.models import User, Group, Permission
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.test import TestCase, Client
from django.urls import reverse
from .models import ODT, Revision, EventoRevision
from .facturacion_models import FacturacionODT, FacturacionContratista, PeriodoFacturacion
from .casos_uso.reapertura_rechazos import deshacer_rechazo
from .casos_uso.edicion_odt import revisar_odt, editar_odt
from .dominio.errores import DatosODTInvalidos, ODTBloqueada
from .consultas.resumen_bandeja import resumen_bandeja
from .consultas.indicadores_bandeja import indicadores_financieros


class ReaperturaRechazosTests(TestCase):
    def setUp(self):
        call_command('configurar_perfiles',stdout=StringIO())
        self.admin=User.objects.create_superuser('admin',password='prueba')
        self.odt=ODT.objects.create(numero=900,tecnico='Proveedor de prueba',contratista='Proveedor de prueba',
            tipo_cliente='B2B',servicio='MANTENCION CORRECTIVA CON COBRO',valor_pago_tecnico=100,
            valor_pago_editado=150,estado_informe='ENVIADO',estado_softguard='Finalizado')
        self.revision=Revision.objects.create(odt=self.odt,estado='RECHAZADA',observacion='Motivo original',actualizado_por=self.admin)
        self.original=EventoRevision.objects.create(odt=self.odt,estado_anterior='APROBADA',estado_nuevo='RECHAZADA',comentario='Motivo original',usuario=self.admin)
        self.url=reverse('reabrir_rechazo')

    def abrir(self,**datos):
        return deshacer_rechazo(self.admin,numero=datos.pop('numero','900'),motivo=datos.pop('motivo','Error revisado por supervisión'),**datos)

    def facturar(self):
        p=PeriodoFacturacion.objects.create(fecha_desde=date(2026,10,21),fecha_hasta=date(2026,11,20))
        f=FacturacionContratista.objects.create(periodo=p,contratista='Proveedor histórico',numero_requisicion='REQ')
        return FacturacionODT.objects.create(facturacion=f,odt=self.odt,servicio_facturado='Histórico',monto_facturado=80)

    def test_reapertura_directa_a_aprobada_con_motivo_y_auditoria_sin_perder_datos(self):
        self.assertEqual(resumen_bandeja(ODT.objects.all())['total']['cantidad'],0)
        resultado=self.abrir()
        self.assertEqual(resultado.estado,'APROBADA')
        self.revision.refresh_from_db();self.odt.refresh_from_db();self.original.refresh_from_db()
        self.assertEqual(self.revision.estado,'APROBADA')
        self.assertEqual(self.revision.actualizado_por,self.admin)
        self.assertEqual((self.odt.valor_pago_tecnico,self.odt.valor_pago_editado,self.odt.estado_informe),(100,150,'ENVIADO'))
        self.assertEqual(self.original.comentario,'Motivo original')
        nuevo=EventoRevision.objects.exclude(pk=self.original.pk).get()
        self.assertEqual((nuevo.estado_anterior,nuevo.estado_nuevo),('RECHAZADA','APROBADA'))
        self.assertIn('Error revisado por supervisión',nuevo.comentario)
        self.assertIn('Motivo original',nuevo.comentario)
        self.assertEqual(nuevo.usuario,self.admin)
        self.assertEqual(resumen_bandeja(ODT.objects.all())['total']['monto'],150)
        financieros=indicadores_financieros(ODT.objects.all())
        self.assertEqual(financieros['aprobadas']['monto'],150)
        self.assertEqual(financieros['rechazadas']['cantidad'],0)

    def test_motivo_obligatorio_y_repeticion_no_duplica_eventos(self):
        with self.assertRaises(DatosODTInvalidos):self.abrir(motivo='  ')
        self.assertEqual(EventoRevision.objects.count(),1)
        self.abrir()
        with self.assertRaises(ODTBloqueada):self.abrir()
        self.assertEqual(EventoRevision.objects.count(),2)

    def test_facturada_sigue_bloqueada_y_conserva_instantanea(self):
        item=self.facturar()
        with self.assertRaises(ODTBloqueada):self.abrir()
        item.refresh_from_db();self.revision.refresh_from_db()
        self.assertEqual(self.revision.estado,'RECHAZADA')
        self.assertEqual((item.servicio_facturado,item.monto_facturado),('Histórico',80))
        self.assertEqual(EventoRevision.objects.count(),1)

    def test_edicion_y_revision_normal_siguen_bloqueadas_hasta_reabrir(self):
        with self.assertRaises(ODTBloqueada):revisar_odt(self.admin,numero=900,estado='APROBADA')
        with self.assertRaises(ODTBloqueada):
            editar_odt(self.admin,numero=900,servicio=self.odt.servicio,monto='200',confirmar_monto=True)
        self.abrir()
        editar_odt(self.admin,numero=900,servicio=self.odt.servicio,monto='200',confirmar_monto=True)
        self.odt.refresh_from_db();self.assertEqual(self.odt.valor_pago_editado,200)

    def test_permisos_y_coordinadores_no_se_amplian(self):
        for grupo in ('Calendario de visitas','Coordinador'):
            u=User.objects.create_user('usuario_'+str(Group.objects.get(name=grupo).pk))
            u.groups.add(Group.objects.get(name=grupo))
            if grupo=='Coordinador':
                u.user_permissions.add(Permission.objects.get(codename='revisar_pago_sstt',content_type__app_label='revisiones'))
            with self.assertRaises(PermissionDenied):deshacer_rechazo(u,numero=900,motivo='Prueba')
        self.revision.refresh_from_db();self.assertEqual(self.revision.estado,'RECHAZADA')
        self.assertEqual(EventoRevision.objects.count(),1)

    def test_yasna_solo_reabre_instalacion_generica_no_cruzverde_ni_otros(self):
        u=User.objects.create_user('consulta_instalacion')
        call_command('habilitar_pagos_instalacion',usuario=u.username,stdout=StringIO())
        self.client.force_login(u)
        for servicio in ('MANTENCION CORRECTIVA CON COBRO','MANTENIMIENTO NUEVA INSTALACION CRUZVERDE'):
            ODT.objects.filter(pk=self.odt.pk).update(servicio=servicio)
            self.assertEqual(self.client.post(self.url,{'numero':'900','motivo':'Revisado'}).status_code,403)
        ODT.objects.filter(pk=self.odt.pk).update(servicio='MANTENIMIENTO NUEVA INSTALACIÓN')
        self.assertEqual(self.client.post(self.url,{'numero':'900','motivo':'Revisado'}).status_code,200)
        self.revision.refresh_from_db();self.assertEqual(self.revision.estado,'APROBADA')

    def test_solo_post_csrf_obligatorio_y_destino_fijo(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(self.url).status_code,405)
        seguro=Client(enforce_csrf_checks=True);seguro.force_login(self.admin)
        self.assertEqual(seguro.post(self.url,{'numero':'900','motivo':'Prueba'}).status_code,403)
        respuesta=self.client.post(self.url,{'numero':'900','motivo':'Error corregido','estado':'EN_REVISION'})
        self.assertEqual(respuesta.status_code,200)
        self.assertEqual(respuesta.json()['estado'],'APROBADA')
        self.assertEqual(self.client.post(self.url,{'numero':'900','motivo':'Repetido'}).status_code,409)

    def test_rechazo_actual_y_auditoria_se_revierten_juntos_si_falla_evento(self):
        with patch('revisiones.casos_uso.reapertura_rechazos.EventoRevision.objects.create',side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):self.abrir()
        self.revision.refresh_from_db()
        self.assertEqual((self.revision.estado,self.revision.observacion),('RECHAZADA','Motivo original'))
        self.assertEqual(EventoRevision.objects.count(),1)

    def test_http_odt_inexistente_y_no_rechazada(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(self.url,{'numero':'999','motivo':'Prueba'}).status_code,404)
        self.revision.estado='EN_REVISION';self.revision.save()
        self.assertEqual(self.client.post(self.url,{'numero':'900','motivo':'Prueba'}).status_code,409)
        self.assertEqual(EventoRevision.objects.count(),1)

    def test_boton_solo_rechazada_no_facturada_y_con_permiso(self):
        self.client.force_login(self.admin)
        parametros={'estado':'','fecha_desde':'','fecha_hasta':'','q':'900',
            'contratistas_filtrados':'1','contratista':'Proveedor de prueba'}
        def consultar():
            with patch('revisiones.vistas.bandeja.coordinadores_para_mostrar',
                       side_effect=lambda r,ns:{n:{'identificado':False} for n in ns}):
                return self.client.get(reverse('bandeja'),parametros)
        respuesta=consultar()
        self.assertEqual(respuesta.status_code,200)
        self.assertContains(respuesta,'class="btn alt deshacer-rechazo"')
        self.facturar()
        respuesta=consultar()
        self.assertNotContains(respuesta,'class="btn alt deshacer-rechazo"')

    def test_historial_visible_conserva_motivos_y_reapertura(self):
        self.abrir()
        self.client.force_login(self.admin)
        with patch('revisiones.vistas.odt.consultar_historial_odt',return_value=[]):
            respuesta=self.client.get(reverse('historial_odt',args=[900]))
        self.assertEqual(respuesta.status_code,200)
        eventos=respuesta.json()['eventos']
        evento=next(e for e in eventos if 'Rechazo deshecho' in e['accion'])
        self.assertIn('Aprobada',evento['accion'])
        self.assertIn('Motivo original',evento['observacion'])
        self.assertIn('Error revisado por supervisión',evento['observacion'])
        self.assertEqual(evento['usuario'],self.admin.username)
