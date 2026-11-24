from datetime import datetime, date, timezone as tzutc
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from django.contrib.auth.models import User, Group, Permission
from django.core.management import call_command
from django.http import QueryDict
from django.test import TestCase
from django.urls import reverse
from io import StringIO
from .models import ODT, CambioSoftGuard, CorreccionODT, Revision
from .casos_uso.sincronizacion import ejecutar_sincronizacion
from .consultas.cambios_softguard import consultar_detecciones
from .facturacion_models import PeriodoFacturacion, FacturacionContratista, FacturacionODT


def fuente(monto=100,servicio='MANTENIMIENTO PREVENTIVO',**extras):
    datos = dict(Numero=901,CuentaCompleta='FIR-0901 - Cliente de prueba',Tecnico='Técnico de prueba',
                Estado='Finalizado',Servicio=servicio,ValorPagoTecnico=monto)
    datos.update(extras)
    return datos


class CambiosSoftGuardTests(TestCase):
    def setUp(self):
        temporal=TemporaryDirectory();self.addCleanup(temporal.cleanup)
        configuracion=self.settings(SSTT_SYNC_LOCK_FILE=str(Path(temporal.name)/'sync.lock'))
        configuracion.enable();self.addCleanup(configuracion.disable)
        self.sincronizar()
        self.odt=ODT.objects.get(numero=901)
        self.admin=User.objects.create_superuser('admin',password='prueba')

    def sincronizar(self,**datos):
        opciones=datos.pop('opciones',{})
        return ejecutar_sincronizacion(lambda:iter([fuente(**datos)]),**opciones)

    def test_alta_inicial_sin_inventar_cambios_y_repeticion_idempotente(self):
        self.assertFalse(CambioSoftGuard.objects.exists())
        self.sincronizar();self.assertFalse(CambioSoftGuard.objects.exists())
        self.sincronizar(monto=250)
        self.assertEqual(CambioSoftGuard.objects.count(),1)
        self.sincronizar(monto=250)
        self.assertEqual(CambioSoftGuard.objects.count(),1)

    def test_monto_y_servicio_con_valores_antes_despues_fecha_deteccion_y_ejecucion(self):
        fijo=datetime(2026,11,24,11,5,6,tzinfo=tzutc.utc)
        with patch('revisiones.casos_uso.sincronizacion.timezone.now',return_value=fijo):
            resultado=self.sincronizar(monto=250,servicio='MANTENIMIENTO RENOVACIÓN',
                FechaModificacion=datetime(2026,1,1,12,tzinfo=tzutc.utc))
        eventos={c.campo:c for c in CambioSoftGuard.objects.all()}
        self.assertEqual((eventos['valor_pago_tecnico'].valor_anterior,eventos['valor_pago_tecnico'].valor_nuevo),('100.00','250.00'))
        self.assertEqual(eventos['servicio'].valor_anterior,'MANTENIMIENTO PREVENTIVO')
        for evento in eventos.values():
            self.assertEqual(evento.detectado_en,fijo)
            self.assertEqual(evento.ejecucion_id,resultado.ejecucion_id)

    def test_preserva_ceros_y_disminuciones(self):
        self.sincronizar(monto=0)
        c=CambioSoftGuard.objects.get()
        self.assertEqual(c.valor_nuevo,'0.00')
        r=consultar_detecciones(QueryDict('sg_campo=valor_pago_tecnico'))
        self.assertEqual(r['filas'][0]['diferencia'],Decimal('-100'))

    def test_solo_origen_no_ediciones_locales_ni_otros_campos(self):
        ODT.objects.filter(pk=self.odt.pk).update(valor_pago_editado=2,servicio_editado='Solicitado')
        self.sincronizar(Tecnico='Otro técnico')
        self.assertFalse(CambioSoftGuard.objects.exists())
        self.sincronizar(monto=300)
        self.assertEqual(CambioSoftGuard.objects.get().valor_anterior,'100.00')
        self.odt.refresh_from_db()
        self.assertEqual(self.odt.valor_pago_editado,2)
        self.assertEqual(self.odt.servicio_editado,'Solicitado')

    def test_simulacion_y_fila_invalida_no_guardan_detecciones(self):
        self.sincronizar(monto=300,opciones={'simular':True})
        self.assertFalse(CambioSoftGuard.objects.exists())
        self.sincronizar(Numero='invalido')
        self.assertFalse(CambioSoftGuard.objects.exists())
        self.odt.refresh_from_db();self.assertEqual(self.odt.valor_pago_tecnico,100)

    def test_auditoria_y_actualizacion_en_misma_transaccion(self):
        with patch('revisiones.casos_uso.sincronizacion.CambioSoftGuard.objects.bulk_create',side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):self.sincronizar(monto=300)
        self.odt.refresh_from_db();self.assertEqual(self.odt.valor_pago_tecnico,100)
        self.assertFalse(CambioSoftGuard.objects.exists())

    def test_preserva_revision_informe_facturas_y_conciliacion_marca_dos(self):
        ODT.objects.filter(pk=self.odt.pk).update(valor_pago_editado=2,estado_informe='ENVIADO')
        CorreccionODT.objects.create(odt=self.odt,corrige_monto=True,monto_objetivo=2,estado='PENDIENTE')
        Revision.objects.create(odt=self.odt,estado='RECHAZADA')
        p=PeriodoFacturacion.objects.create(fecha_desde=date(2026,10,21),fecha_hasta=date(2026,11,20))
        f=FacturacionContratista.objects.create(periodo=p,contratista='Proveedor histórico')
        item=FacturacionODT.objects.create(facturacion=f,odt=self.odt,servicio_facturado='Histórico',monto_facturado=80)
        self.sincronizar(monto=300)
        self.odt.refresh_from_db();item.refresh_from_db()
        self.assertIsNone(self.odt.valor_pago_editado)
        self.assertEqual(self.odt.seguimiento_correccion.estado,'ACTUALIZADA')
        self.assertEqual(self.odt.revision.estado,'RECHAZADA')
        self.assertEqual(self.odt.estado_informe,'ENVIADO')
        self.assertEqual((item.servicio_facturado,item.monto_facturado),('Histórico',80))
        self.assertEqual(CambioSoftGuard.objects.get().valor_anterior,'100.00')

    def evento(self,fecha,numero=901,campo='valor_pago_tecnico'):
        odt,_=ODT.objects.get_or_create(numero=numero)
        return CambioSoftGuard.objects.create(odt=odt,campo=campo,valor_anterior='100.00',valor_nuevo='250.00',detectado_en=fecha)

    def test_filtros_fecha_chile_inclusivos_y_odt_con_dos_campos(self):
        # En noviembre UTC-3: el día local comienza a las 03:00 UTC.
        self.evento(datetime(2026,11,24,2,59,59,tzinfo=tzutc.utc))
        self.evento(datetime(2026,11,24,3,tzinfo=tzutc.utc))
        self.evento(datetime(2026,11,25,2,59,59,tzinfo=tzutc.utc),campo='servicio')
        self.evento(datetime(2026,11,25,3,tzinfo=tzutc.utc),numero=902)
        r=consultar_detecciones(QueryDict('sg_desde=2026-11-24&sg_hasta=2026-11-24&sg_odt=901'))
        self.assertEqual((r['cantidad'],r['cantidad_odt']),(2,1))
        r=consultar_detecciones(QueryDict('sg_desde=2026-11-24&sg_hasta=2026-11-24&sg_campo=servicio'))
        self.assertEqual(r['cantidad'],1)

    def test_filtros_invalidos_cierran_resultado_y_paginacion_conserva_filtros(self):
        for query in ('sg_desde=no-fecha','sg_desde=2026-11-25&sg_hasta=2026-11-24','sg_campo=otro','sg_odt=abc'):
            r=consultar_detecciones(QueryDict(query));self.assertEqual(r['cantidad'],0);self.assertTrue(r['errores'])
        for _ in range(51):self.evento(datetime(2026,11,24,11,tzinfo=tzutc.utc))
        r=consultar_detecciones(QueryDict('sg_odt=901&sg_campo=valor_pago_tecnico&page_detalle=2'))
        self.assertEqual(len(r['filas']),1)
        self.assertIn('sg_odt=901',r['querystring'])
        self.assertNotIn('page_detalle',r['querystring'])

    def test_seguimiento_muestra_deteccion_aunque_no_haya_correccion_manual(self):
        self.sincronizar(monto=300)
        self.client.force_login(self.admin)
        with patch('revisiones.vistas.correcciones.coordinadores_para_mostrar',return_value={}), \
             patch('revisiones.vistas.correcciones.catalogo_coordinadores',return_value={}):
            r=self.client.get(reverse('odt_modificadas'),{'sg_odt':'901'})
        self.assertEqual(r.status_code,200)
        self.assertContains(r,'Cambios detectados en SoftGuard')
        self.assertContains(r,'$100')
        self.assertContains(r,'$300')
        self.assertEqual(r.context['cantidad'],0)
        self.assertEqual(r.context['detecciones']['cantidad'],1)

    def test_ultima_deteccion_en_fila_y_sin_registro_para_anteriores(self):
        ODT.objects.filter(pk=self.odt.pk).update(valor_pago_editado=2)
        self.sincronizar(monto=300)
        otro=ODT.objects.create(numero=902,valor_pago_editado=2)
        self.client.force_login(self.admin)
        with patch('revisiones.vistas.correcciones.coordinadores_para_mostrar',
                   side_effect=lambda r,ns:{n:{'nombre':'Prueba','identificado':False} for n in ns}), \
             patch('revisiones.vistas.correcciones.catalogo_coordinadores',return_value={}):
            r=self.client.get(reverse('odt_modificadas'))
        filas={f['numero']:f for f in r.context['filas']}
        self.assertEqual(filas[901]['ultima_deteccion_softguard'],CambioSoftGuard.objects.get().detectado_en)
        self.assertIsNone(filas[902]['ultima_deteccion_softguard'])
        self.assertContains(r,'Sin registro')

    def test_calendario_sin_acceso_y_usuario_sin_montos_sin_historial_financiero(self):
        call_command('configurar_perfiles',stdout=StringIO())
        u=User.objects.create_user('consulta_general')
        u.groups.add(Group.objects.get(name='Calendario de visitas'))
        self.client.force_login(u)
        self.assertEqual(self.client.get(reverse('odt_modificadas')).status_code,403)

        self.sincronizar(monto=300)
        otro=User.objects.create_user('consulta_sin_montos')
        otro.user_permissions.add(Permission.objects.get(codename='ver_bandeja_sstt',content_type__app_label='revisiones'))
        self.client.force_login(otro)
        with patch('revisiones.vistas.correcciones.catalogo_coordinadores',return_value={}), \
             patch('revisiones.vistas.correcciones.coordinadores_para_mostrar',return_value={}):
            respuesta=self.client.get(reverse('odt_modificadas'))
        self.assertEqual(respuesta.status_code,200)
        self.assertIsNone(respuesta.context['detecciones'])
        self.assertNotContains(respuesta,'Cambios detectados en SoftGuard')

    def test_lote_confirmado_conserva_deteccion_si_falla_el_siguiente(self):
        def origen():
            yield fuente(monto=300)
            raise RuntimeError('Origen interrumpido')
        with self.assertRaises(RuntimeError):
            ejecutar_sincronizacion(origen,tamano_lote=1)
        cambio=CambioSoftGuard.objects.get()
        self.assertEqual(cambio.ejecucion.estado,'FALLIDA')
        self.odt.refresh_from_db();self.assertEqual(self.odt.valor_pago_tecnico,300)
        self.sincronizar(monto=300)
        self.assertEqual(CambioSoftGuard.objects.count(),1)

    def test_cambio_de_regreso_conserva_ambas_detecciones_sin_reescribir_fecha(self):
        self.sincronizar(monto=300)
        primero=CambioSoftGuard.objects.get()
        self.sincronizar(monto=100)
        primero.refresh_from_db()
        self.assertEqual(CambioSoftGuard.objects.count(),2)
        ultimo=CambioSoftGuard.objects.first()
        self.assertEqual((ultimo.valor_anterior,ultimo.valor_nuevo),('300.00','100.00'))
        self.assertGreaterEqual(ultimo.detectado_en,primero.detectado_en)
