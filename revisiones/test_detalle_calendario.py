from datetime import date, datetime
from decimal import Decimal
from io import StringIO
from unittest.mock import patch
from django.contrib.auth.models import User, Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from .models import ODT, Revision, EventoRevision
from .dominio.detalle_tecnico import texto_tecnico

SQL = 'revisiones.vistas.detalle_calendario.consultar_historial_odt'


class DetalleCalendarioTests(TestCase):
    def setUp(self):
        call_command('configurar_perfiles',stdout=StringIO())
        self.usuario=User.objects.create_user('consulta_interna',password='prueba')
        call_command('habilitar_calendario_internos',usuario=self.usuario.username,stdout=StringIO())
        self.client.force_login(self.usuario)
        for numero,tecnico in ((1,'T. INTERNO - ServicioStgo'),(2,'T. INTERNO - ServicioViña'),
                               (3,'T. EXTERNO - Técnico de prueba'),(4,'')):
            ODT.objects.create(numero=numero,tecnico=tecnico,contratista='T. INTERNO - ServicioStgo',
                cuenta_completa=f'Cuenta de prueba {numero}',estado_softguard='Finalizado',
                fecha_visita=date(2026,11,10),servicio='MANTENIMIENTO PREVENTIVO',
                observaciones_insumos='Revisar cámara y conexión.',valor_pago_tecnico=987654,
                valor_pago_editado=876543)
        self.url=reverse('detalle_calendario',args=[1])

    def test_enlace_solo_para_perfil_interno_y_regreso_con_filtros(self):
        calendario=reverse('calendario_servicios')
        r=self.client.get(calendario,{'mes':'2026-11','q':'Cuenta','categoria':'realizadas'})
        self.assertContains(r,self.url)
        self.assertNotContains(r,reverse('detalle_calendario',args=[3]))
        volver=calendario+'?mes=2026-11&q=Cuenta&categoria=realizadas'
        with patch(SQL,return_value=[]):r=self.client.get(self.url,{'volver':volver})
        self.assertEqual(r.context['volver_calendario'],volver)
        self.assertContains(r,'Volver al calendario')
        self.assertTrue(r['Cache-Control'].find('no-store')>=0)

    def test_detalle_e_historial_ambos_internos_sin_montos_ni_auditoria_financiera(self):
        odt=ODT.objects.get(numero=1)
        Revision.objects.create(odt=odt,estado='RECHAZADA')
        EventoRevision.objects.create(odt=odt,estado_anterior='APROBADA',estado_nuevo='RECHAZADA',
                                     comentario='Pago privado 765432')
        movimientos=[{'FechaHora':datetime(2026,11,10,12),'Accion':'Observacion',
            'Observacion':'Se reemplaza conector. Costo $65.000. Queda operativo.',
            'NombreUsuario':'Técnico de prueba','CorreoUsuario':'privado@example.com'},
            {'FechaHora':datetime(2026,11,11,12),'Accion':'Pago técnico','Observacion':'876543'}]
        with patch(SQL,return_value=movimientos) as sql:
            r=self.client.get(self.url)
        sql.assert_called_once_with(1)
        self.assertEqual(r.status_code,200)
        self.assertContains(r,'Se reemplaza conector.')
        self.assertContains(r,'Queda operativo.')
        self.assertContains(r,'Contenido administrativo omitido')
        for privado in ('987654','876543','765432','65.000','privado@example.com','RECHAZADA'):
            self.assertNotContains(r,privado)
        self.assertNotIn('odt',r.context)
        for numero in (1,2):
            with patch(SQL,return_value=[]):
                self.assertEqual(self.client.get(reverse('detalle_calendario',args=[numero])).status_code,200)

    def test_odt_fuera_de_alcance_y_sin_visita_no_consultan_sql(self):
        ODT.objects.filter(numero=2).update(fecha_visita=None)
        for numero in (2,3,4,9999):
            with patch(SQL) as sql:
                self.assertEqual(self.client.get(reverse('detalle_calendario',args=[numero])).status_code,404)
            sql.assert_not_called()

    def test_reasignacion_a_externo_revoca_detalle_en_siguiente_peticion(self):
        with patch(SQL,return_value=[]):self.assertEqual(self.client.get(self.url).status_code,200)
        ODT.objects.filter(numero=1).update(tecnico='T. EXTERNO - Otro técnico')
        with patch(SQL) as sql:self.assertEqual(self.client.get(self.url).status_code,404)
        sql.assert_not_called()

    def test_otros_usuarios_calendario_no_reciben_nuevo_acceso(self):
        otro=User.objects.create_user('consulta_general')
        otro.groups.add(Group.objects.get(name='Calendario de visitas'))
        self.client.force_login(otro)
        with patch(SQL) as sql:self.assertEqual(self.client.get(self.url).status_code,403)
        sql.assert_not_called()
        r=self.client.get(reverse('calendario_servicios'),{'mes':'2026-11'})
        self.assertNotContains(r,self.url)

    def test_usuario_sin_permiso_e_inactivo_no_reciben_datos(self):
        self.usuario.groups.clear()
        with patch(SQL) as sql:self.assertEqual(self.client.get(self.url).status_code,403)
        sql.assert_not_called()
        self.client.logout()
        with patch(SQL) as sql:self.assertEqual(self.client.get(self.url).status_code,302)
        sql.assert_not_called()

    def test_sin_operaciones_de_escritura_ni_historial_financiero(self):
        with patch(SQL) as sql:self.assertEqual(self.client.post(self.url,{}).status_code,405)
        sql.assert_not_called()
        for nombre,datos in (('guardar_fila',{'numero':1,'monto':'0'}),
                             ('actualizar_revision',{'numero':1,'estado':'APROBADA'}),
                             ('actualizar_informe',{'numero':1,'estado':'ENVIADO'})):
            self.assertEqual(self.client.post(reverse(nombre),datos).status_code,403)
        self.assertEqual(self.client.get(reverse('historial_odt',args=[1])).status_code,403)
        self.assertEqual(self.client.get(reverse('detalle',args=[1])).status_code,403)
        self.assertEqual(self.client.get(reverse('historial_facturacion')).status_code,403)
        self.assertEqual(ODT.objects.get(numero=1).valor_pago_editado,Decimal('876543'))
        self.assertEqual(ODT.objects.get(numero=1).estado_informe,'NO_ENVIADO')

    def test_falla_sql_conserva_detalle_sin_filtrar_error(self):
        with patch(SQL,side_effect=RuntimeError('password=secreto')):r=self.client.get(self.url)
        self.assertEqual(r.status_code,200)
        self.assertContains(r,'no está disponible temporalmente')
        self.assertContains(r,'Revisar cámara y conexión.')
        self.assertNotContains(r,'secreto')

    def test_regreso_no_acepta_destinos_externos_y_textos_escapados(self):
        for volver in ('https://example.com/','//example.com/','//[invalido','/guardar-fila/'):
            with patch(SQL,return_value=[]):r=self.client.get(self.url,{'volver':volver})
            self.assertEqual(r.context['volver_calendario'],reverse('calendario_servicios'))
        with patch(SQL,return_value=[{'Accion':'Observacion','Observacion':'<script>alert(1)</script>'}]):
            r=self.client.get(self.url)
        self.assertNotContains(r,'<script>alert(1)</script>')
        self.assertContains(r,'&lt;script&gt;')

    def test_texto_tecnico_suprime_importes_y_fragmentos_administrativos(self):
        for texto in ('Monto 20000','Transferencia bancaria 12345678','CLP 15000','USD 100',
                      'total 25.000','precio 30000','pago realizado'):
            self.assertEqual(texto_tecnico(texto),'[Contenido administrativo omitido]')
        self.assertEqual(texto_tecnico('Fuente 12 V 10 A operativa.'),'Fuente 12 V 10 A operativa.')

    def test_usuario_inactivo_no_puede_consultar(self):
        self.usuario.is_active=False;self.usuario.save()
        with patch(SQL) as sql:self.assertEqual(self.client.get(self.url).status_code,302)
        sql.assert_not_called()

    def test_coordinador_sin_vinculo_no_amplia_alcance_por_el_nuevo_grupo(self):
        self.usuario.groups.add(Group.objects.get(name='Coordinador'))
        with patch(SQL) as sql:self.assertEqual(self.client.get(self.url).status_code,404)
        sql.assert_not_called()
