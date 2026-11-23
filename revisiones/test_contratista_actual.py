from contextlib import closing
from datetime import date, datetime
from io import StringIO
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase, SimpleTestCase, RequestFactory
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django.http import QueryDict
from .casos_uso.sincronizacion import ejecutar_sincronizacion
from .casos_uso.contratistas_odt import reparar_lote_contratistas
from .casos_uso.facturacion import previsualizar, confirmar
from .consultas.filtros_bandeja import filtrar_tabla
from .consultas.exportacion_pdf import odts_aprobadas
from .dominio.facturacion import SeleccionFacturacion, FacturacionInvalida
from .dominio.contratistas_odt import contratista_desde_tecnico
from .facturacion_models import FacturacionODT, FacturacionContratista, PeriodoFacturacion
from .models import ODT, Revision, EventoRevision, AsignacionCoordinadorODT
from .management.commands.reparar_contratistas_odt import respaldar_sqlite

TECNICO_ACTUAL='T. EXTERNO - Técnico de prueba'


class ContratistaActualTests(TestCase):
    def setUp(self):
        self.temporal=TemporaryDirectory();self.addCleanup(self.temporal.cleanup)
        self.configuracion=self.settings(SSTT_SYNC_LOCK_FILE=str(Path(self.temporal.name)/'sync.lock'))
        self.configuracion.enable();self.addCleanup(self.configuracion.disable)
        self.admin=User.objects.create_superuser('admin',password='test')
        self.fecha=timezone.make_aware(datetime(2026,11,5,12))

    def fuente(self,tecnico=TECNICO_ACTUAL):
        return {'Numero':901,'Tecnico':tecnico,'CuentaCompleta':'FIR-0001 - Cliente de prueba',
                'Servicio':'MANTENCION CORRECTIVA SIN COBRO','Estado':'Finalizado',
                'ValorPagoTecnico':100,'FechaFinalizacion':self.fecha}

    def sincronizar(self,tecnico=TECNICO_ACTUAL,**opciones):
        return ejecutar_sincronizacion(lambda:iter([self.fuente(tecnico)]),**opciones)

    def preparar(self):
        self.sincronizar()
        ODT.objects.filter(numero=901).update(contratista='Responsable anterior')
        return ODT.objects.get(numero=901)

    def test_sigue_cambio_de_tecnico_en_softguard_y_es_idempotente(self):
        self.sincronizar('Responsable anterior')
        self.sincronizar()
        odt=ODT.objects.get(numero=901)
        self.assertEqual((odt.tecnico,odt.contratista),(TECNICO_ACTUAL,TECNICO_ACTUAL))
        evento=odt.eventos_revision.get()
        self.assertIn('Responsable anterior',evento.comentario)
        self.assertIn(TECNICO_ACTUAL,evento.comentario)
        self.assertEqual(evento.estado_anterior,evento.estado_nuevo)
        self.assertEqual(self.sincronizar().sin_cambios,1)
        self.assertEqual(EventoRevision.objects.count(),1)

    def test_repara_diferencia_aunque_el_origen_no_haya_cambiado(self):
        self.preparar()
        self.assertEqual(self.sincronizar().actualizadas,1)
        self.assertEqual(ODT.objects.get(numero=901).contratista,TECNICO_ACTUAL)

    def test_simulacion_no_escribe_cambios_ni_auditoria(self):
        odt=self.preparar()
        with CaptureQueriesContext(connection) as consultas:
            resultado=self.sincronizar(simular=True)
        self.assertEqual(resultado.actualizadas,1)
        self.assertFalse(any(c['sql'].split()[0] in {'INSERT','UPDATE','DELETE'} for c in consultas))
        odt.refresh_from_db()
        self.assertEqual(odt.contratista,'Responsable anterior')
        self.assertFalse(EventoRevision.objects.exists())

    def test_no_borra_asignacion_si_origen_no_informa_tecnico(self):
        self.preparar()
        self.sincronizar('  ')
        self.assertEqual(ODT.objects.get(numero=901).contratista,'Responsable anterior')
        self.assertFalse(EventoRevision.objects.exists())

    def test_reparacion_local_preserva_ediciones_revision_coordinador_e_instantanea(self):
        odt=self.preparar()
        ODT.objects.filter(pk=odt.pk).update(servicio_editado='Servicio corregido',valor_pago_editado=0,estado_informe='ENVIADO')
        Revision.objects.create(odt=odt,estado='RECHAZADA')
        AsignacionCoordinadorODT.objects.create(odt=odt,usuario_coordinador='coordinadora_prueba')
        periodo=PeriodoFacturacion.objects.create(fecha_desde=date(2026,10,21),fecha_hasta=date(2026,11,20))
        factura=FacturacionContratista.objects.create(periodo=periodo,contratista='Proveedor histórico',numero_requisicion='REQ')
        item=FacturacionODT.objects.create(odt=odt,facturacion=factura,servicio_facturado='Histórico',monto_facturado=800)
        self.assertEqual(reparar_lote_contratistas([odt.pk],aplicar=True),[(901,'Responsable anterior',TECNICO_ACTUAL)])
        odt.refresh_from_db();factura.refresh_from_db();item.refresh_from_db()
        self.assertEqual(odt.contratista,TECNICO_ACTUAL)
        self.assertEqual((odt.servicio_editado,odt.valor_pago_editado,odt.estado_informe),('Servicio corregido',0,'ENVIADO'))
        self.assertEqual(odt.revision.estado,'RECHAZADA')
        self.assertEqual(odt.asignacion_coordinador.usuario_coordinador,'coordinadora_prueba')
        self.assertEqual((factura.contratista,factura.numero_requisicion),('Proveedor histórico','REQ'))
        self.assertEqual((item.servicio_facturado,item.monto_facturado),('Histórico',800))
        self.assertEqual(odt.eventos_revision.get().estado_nuevo,'RECHAZADA')
        self.assertEqual(reparar_lote_contratistas([odt.pk],aplicar=True),[])
        self.assertEqual(EventoRevision.objects.count(),1)

    def test_filtro_pdf_y_facturacion_pendiente_usan_contratista_correcto(self):
        odt=self.preparar()
        reparar_lote_contratistas([odt.pk],aplicar=True)
        consulta=filtrar_tabla(ODT.objects.all(),filtros={
            'estado':'Finalizado','revision':'','q':'901','fecha_desde':'2026-10-21','fecha_hasta':'2026-11-20'},
            servicios_seleccionados=[],contratistas_seleccionados=[TECNICO_ACTUAL],campo_fecha='fecha_finalizacion',
            por_creacion=False,numero_exacto=None,avisar_fecha=lambda v:None)
        self.assertEqual(list(consulta.values_list('numero',flat=True)),[901])
        self.assertEqual([o.numero for o in odts_aprobadas(TECNICO_ACTUAL,date(2026,10,21),date(2026,11,20))],[901])
        seleccion=SeleccionFacturacion(date(2026,10,21),date(2026,11,20),contratistas=(TECNICO_ACTUAL,))
        vista=previsualizar(self.admin,seleccion)
        self.assertEqual(vista.resumen[0]['contratista'],TECNICO_ACTUAL)
        confirmar(self.admin,seleccion,requisiciones={TECNICO_ACTUAL:'REQ'},confirmacion=vista.confirmacion)
        self.assertEqual(FacturacionContratista.objects.get().contratista,TECNICO_ACTUAL)

    def test_reparacion_invalida_previsualizacion_anterior(self):
        odt=self.preparar()
        seleccion=SeleccionFacturacion(date(2026,10,21),date(2026,11,20))
        vista=previsualizar(self.admin,seleccion)
        reparar_lote_contratistas([odt.pk],aplicar=True)
        with self.assertRaises(FacturacionInvalida):
            confirmar(self.admin,seleccion,requisiciones={'Responsable anterior':'REQ'},confirmacion=vista.confirmacion)
        self.assertFalse(FacturacionODT.objects.exists())

    def test_actualizacion_y_evento_se_revierten_si_falla_auditoria(self):
        self.preparar()
        with patch('revisiones.casos_uso.sincronizacion.registrar_cambios_contratista',side_effect=RuntimeError):
            with self.assertRaises(RuntimeError): self.sincronizar()
        self.assertEqual(ODT.objects.get(numero=901).contratista,'Responsable anterior')
        self.assertFalse(EventoRevision.objects.exists())

    def test_comando_simula_por_defecto_y_exige_respaldo_para_aplicar(self):
        self.preparar();salida=StringIO()
        with patch('revisiones.servicios_sql.iterar_odts_completas') as origen:
            call_command('reparar_contratistas_odt',stdout=salida)
        origen.assert_not_called()
        self.assertIn('Diferencias detectadas (simulación): 1',salida.getvalue())
        self.assertFalse(EventoRevision.objects.exists())
        with self.assertRaises(CommandError): call_command('reparar_contratistas_odt',aplicar=True)
        self.assertEqual(ODT.objects.get(numero=901).contratista,'Responsable anterior')

    def test_comando_aplica_solo_tras_respaldo_y_es_idempotente(self):
        self.preparar()
        for i in range(2):
            salida=StringIO()
            with patch('revisiones.management.commands.reparar_contratistas_odt.respaldar_sqlite',return_value=Path('respaldo.sqlite3')) as respaldo:
                call_command('reparar_contratistas_odt',aplicar=True,respaldo='respaldo.sqlite3',stdout=salida)
            respaldo.assert_called_once()
            self.assertIn(f'Actualizadas: {1 if i==0 else 0}',salida.getvalue())
        self.assertEqual(EventoRevision.objects.count(),1)

    def test_comando_no_repara_si_falla_respaldo(self):
        self.preparar()
        with patch('revisiones.management.commands.reparar_contratistas_odt.respaldar_sqlite',side_effect=CommandError('falló')):
            with self.assertRaises(CommandError):
                call_command('reparar_contratistas_odt',aplicar=True,respaldo='respaldo.sqlite3',stdout=StringIO())
        self.assertEqual(ODT.objects.get(numero=901).contratista,'Responsable anterior')
        self.assertFalse(EventoRevision.objects.exists())

    def test_historial_muestra_valor_anterior_y_nuevo(self):
        odt=self.preparar();reparar_lote_contratistas([odt.pk],aplicar=True)
        self.client.force_login(self.admin)
        with patch('revisiones.vistas.odt.consultar_historial_odt',return_value=[]):
            respuesta=self.client.get('/historial/901/')
        self.assertEqual(respuesta.status_code,200)
        evento=respuesta.json()['eventos'][0]
        self.assertEqual(evento['accion'],'SSTT · Contratista actualizado')
        self.assertIn('Responsable anterior',evento['observacion'])
        self.assertIn(TECNICO_ACTUAL,evento['observacion'])


    def test_reparacion_en_lotes_y_muestra_limitada(self):
        ODT.objects.bulk_create([ODT(numero=n,tecnico=TECNICO_ACTUAL,contratista='Anterior') for n in range(1,302)])
        salida=StringIO()
        with patch('revisiones.management.commands.reparar_contratistas_odt.respaldar_sqlite',return_value=Path('respaldo.sqlite3')):
            call_command('reparar_contratistas_odt',aplicar=True,respaldo='respaldo.sqlite3',stdout=salida)
        self.assertEqual(ODT.objects.filter(contratista=TECNICO_ACTUAL).count(),301)
        self.assertEqual(EventoRevision.objects.count(),301)
        self.assertIn('Actualizadas: 301',salida.getvalue())
        self.assertEqual(salida.getvalue().count(' -> '),20)

    def test_no_inicia_si_hay_otra_sincronizacion_activa(self):
        self.preparar()
        from .integraciones.bloqueo_sync import SincronizacionEnCurso
        with patch('revisiones.management.commands.reparar_contratistas_odt.bloquear_sincronizacion',side_effect=SincronizacionEnCurso('en curso')), \
             patch('revisiones.management.commands.reparar_contratistas_odt.respaldar_sqlite') as respaldo:
            with self.assertRaises(CommandError):
                call_command('reparar_contratistas_odt',aplicar=True,respaldo='respaldo.sqlite3',stdout=StringIO())
        respaldo.assert_not_called()
        self.assertEqual(ODT.objects.get(numero=901).contratista,'Responsable anterior')

    def test_bandeja_filtrada_por_tecnico_actual_muestra_coordinador_en_su_columna(self):
        odt=self.preparar();reparar_lote_contratistas([odt.pk],aplicar=True)
        request=RequestFactory().get('/',{'q':'901','fecha_desde':'2026-10-21','fecha_hasta':'2026-11-20',
            'contratista':TECNICO_ACTUAL,'contratistas_filtrados':'1'})
        request.user=self.admin
        from .vistas.bandeja import bandeja
        with patch('revisiones.vistas.bandeja.coordinadores_para_mostrar',return_value={901:{'identificado':True,'nombre':'Responsable anterior','usuario':'coordinadora_prueba'}}), \
             patch('revisiones.vistas.bandeja.render',side_effect=lambda r,t,c:c):
            contexto=bandeja(request)
        self.assertEqual([o.numero for o in contexto['registros']],[901])
        from django.template.loader import render_to_string
        html=render_to_string('revisiones/bandeja.html',contexto,request=request)
        celda=html.split('<td class="technician">',1)[1].split('</td>',1)[0]
        self.assertIn(TECNICO_ACTUAL,celda)
        self.assertNotIn('Responsable anterior',celda)
        coordinador=html.split('<td class="coordinador-odt">',1)[1].split('</td>',1)[0]
        self.assertIn('Responsable anterior',coordinador)


class ContratistaDominioTests(SimpleTestCase):
    def test_nombres_vacios_y_limite_del_campo(self):
        self.assertEqual(contratista_desde_tecnico('  Nombre  ','Anterior'),'Nombre')
        self.assertEqual(contratista_desde_tecnico(None,'Anterior'),'Anterior')
        self.assertEqual(len(contratista_desde_tecnico('A'*200)),150)

    def test_respaldo_sqlite_real_verificado_y_sin_sobrescritura(self):
        with TemporaryDirectory() as directorio:
            origen=Path(directorio)/'origen.sqlite3';destino=Path(directorio)/'respaldo.sqlite3'
            with closing(sqlite3.connect(origen)) as bd:
                bd.execute('CREATE TABLE dato (valor TEXT)');bd.execute("INSERT INTO dato VALUES ('persistente')");bd.commit()
                conexion=SimpleNamespace(vendor='sqlite',settings_dict={'NAME':str(origen)},connection=bd,ensure_connection=lambda:None)
                with patch('revisiones.management.commands.reparar_contratistas_odt.connection',conexion):
                    self.assertEqual(respaldar_sqlite(destino),destino.resolve())
                    with self.assertRaises(CommandError): respaldar_sqlite(destino)
                    with self.assertRaises(CommandError): respaldar_sqlite(origen)
            with closing(sqlite3.connect(destino)) as bd:
                self.assertEqual(bd.execute('PRAGMA integrity_check').fetchone(),('ok',))
                self.assertEqual(bd.execute('SELECT valor FROM dato').fetchall(),[('persistente',)])
