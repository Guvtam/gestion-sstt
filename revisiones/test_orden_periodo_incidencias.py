"""Orden global, período por pendientes elegibles y referencia histórica de incidencias."""
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from io import StringIO, BytesIO
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from django.contrib.auth.models import User, Group
from django.core.management import call_command
from django.http import QueryDict
from django.test import TestCase, SimpleTestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook
from .models import ODT, Revision, CorreccionODT
from .facturacion_models import PeriodoFacturacion, FacturacionContratista, FacturacionODT
from .consultas.periodo_bandeja import periodo_inicial
from .consultas.orden_bandeja import leer_orden
from .consultas.filas_bandeja import paginar_filas
from .consultas.fallos_prueba import marcar_fallos
from .dominio.servicios import SERVICIOS_PRINCIPALES
from .acceso_instalacion import SERVICIO_INSTALACION
from .indicadores_odt import con_indicadores_odt
from .metricas_analisis import cargar_metricas


def fecha(dia, hora=12):
    return timezone.make_aware(datetime.combine(dia, time(hora)))


def resolver(request, numeros):
    return {n:{'identificado':True,'nombre':'Josué Tapia','usuario':'jtapia'} for n in numeros}


class PeriodoInicialTests(TestCase):
    def setUp(self):
        self.usuario=User.objects.create_superuser('admin',password='prueba')
        self.hoy=date(2026,11,25)
        self.periodo=PeriodoFacturacion.objects.create(fecha_desde=date(2026,10,21),fecha_hasta=date(2026,11,20))
        self.factura=FacturacionContratista.objects.create(periodo=self.periodo,contratista='Prueba',numero_requisicion='REQ')
        self.a=self.crear(1)
        self.b=self.crear(2,contratista='Otro')

    def crear(self, n, **datos):
        valores=dict(estado_softguard='Finalizado',fecha_finalizacion=fecha(date(2026,11,20)),
            servicio=SERVICIOS_PRINCIPALES[0],contratista='Prueba',valor_pago_tecnico=100)
        valores.update(datos)
        return ODT.objects.create(numero=n,**valores)

    def facturar(self, odt, servicio=None):
        return FacturacionODT.objects.create(odt=odt,facturacion=self.factura,
            servicio_facturado=servicio or odt.servicio,monto_facturado=100)

    def inicial(self, **kwargs):
        return periodo_inicial(self.usuario,self.hoy,**kwargs)

    def test_sin_facturacion_y_cabecera_vacia_mantienen_periodo(self):
        self.assertEqual(self.inicial(),(date(2026,10,21),date(2026,11,20)))
        ODT.objects.all().delete()
        self.assertEqual(self.inicial(),(date(2026,10,21),date(2026,11,20)))

    def test_facturacion_parcial_con_otro_contratista_conserva_periodo(self):
        self.facturar(self.a)
        self.assertEqual(self.inicial(),(date(2026,10,21),date(2026,11,20)))
        self.assertFalse(self.b.item_facturacion if hasattr(self.b,'item_facturacion') else False)

    def test_completa_avanza_desde_21_hasta_hoy_sin_cambiar_instantaneas(self):
        self.facturar(self.a);self.facturar(self.b)
        self.assertEqual(self.inicial(),(date(2026,11,21),self.hoy))
        self.assertEqual(FacturacionODT.objects.count(),2)
        self.assertEqual(sum(FacturacionODT.objects.values_list('monto_facturado',flat=True)),200)

    def test_rechazada_no_bloquea_pero_sin_revision_y_por_revisar_si(self):
        self.facturar(self.a)
        revision=Revision.objects.create(odt=self.b,estado='POR_REVISAR')
        self.assertEqual(self.inicial()[0],date(2026,10,21))
        revision.estado='RECHAZADA';revision.save()
        self.assertEqual(self.inicial()[0],date(2026,11,21))

    def test_elegibilidad_no_cambia_por_monto_cero_ni_servicio_editado(self):
        self.facturar(self.a)
        ODT.objects.filter(pk=self.b.pk).update(valor_pago_editado=0,servicio='OTRO',servicio_editado=SERVICIOS_PRINCIPALES[1])
        self.assertEqual(self.inicial()[0],date(2026,10,21))
        ODT.objects.filter(pk=self.b.pk).update(servicio_editado='OTRO')
        self.assertEqual(self.inicial()[0],date(2026,11,21))

    def test_sin_contratista_y_otro_estado_no_son_facturables(self):
        self.facturar(self.a)
        ODT.objects.filter(pk=self.b.pk).update(contratista='')
        self.crear(3,estado_softguard='Asignado')
        self.crear(4,fecha_finalizacion=fecha(date(2026,11,21)))
        self.assertEqual(self.inicial()[0],date(2026,11,21))

    def test_no_adelanta_periodo_antes_del_21(self):
        self.facturar(self.a);self.facturar(self.b)
        for dia in (1,19,20):
            self.assertEqual(periodo_inicial(self.usuario,date(2026,11,dia)),(date(2026,10,21),date(2026,11,20)))
        self.assertEqual(periodo_inicial(self.usuario,date(2026,11,21)),(date(2026,11,21),date(2026,11,21)))

    def test_cambio_de_anio_y_febrero_bisiesto(self):
        self.assertEqual(periodo_inicial(self.usuario,date(2027,1,5)),(date(2026,12,21),date(2027,1,20)))
        self.assertEqual(periodo_inicial(self.usuario,date(2028,2,29)),(date(2028,1,21),date(2028,2,20)))

    def test_instalacion_tiene_su_propio_alcance_y_no_incluye_cruzverde(self):
        usuario=User.objects.create_user('mixta');usuario.groups.add(Group.objects.get_or_create(name='Coordinador')[0])
        call_command('habilitar_pagos_instalacion',usuario='mixta',stdout=StringIO())
        generic=self.crear(3,servicio=SERVICIO_INSTALACION)
        self.crear(4,servicio='MANTENIMIENTO NUEVA INSTALACION CRUZVERDE')
        self.assertEqual(periodo_inicial(usuario,self.hoy,instalacion=True)[0],date(2026,10,21))
        self.facturar(generic)
        self.assertEqual(periodo_inicial(usuario,self.hoy,instalacion=True)[0],date(2026,11,21))
        self.assertEqual(self.inicial()[0],date(2026,10,21))

    def test_entrada_parcial_completa_y_consulta_abierta_conserva_fechas(self):
        self.client.force_login(self.usuario)
        with patch('revisiones.vistas.bandeja.timezone.localdate', return_value=self.hoy), \
             patch('revisiones.vistas.bandeja.coordinadores_para_mostrar', side_effect=resolver):
            inicial=self.client.get(reverse('bandeja'))
            self.assertEqual(inicial.context['filtros']['fecha_hasta'],'2026-11-20')
            url_abierta=inicial.context['url_consulta']
            self.facturar(self.a)
            parcial=self.client.get(reverse('bandeja'))
            self.assertEqual(parcial.context['filtros']['fecha_desde'],'2026-10-21')
            self.facturar(self.b)
            completa=self.client.get(reverse('bandeja'))
            self.assertEqual(completa.context['filtros']['fecha_desde'],'2026-11-21')
            self.assertEqual(completa.context['filtros']['fecha_hasta'],'2026-11-25')
            abierta=self.client.get(url_abierta)
            self.assertEqual(abierta.context['filtros']['fecha_desde'],'2026-10-21')
            self.assertEqual(abierta.context['filtros']['fecha_hasta'],'2026-11-20')

    def test_sin_cabecera_no_adelanta_aunque_no_queden_odt(self):
        self.factura.delete();self.periodo.delete();ODT.objects.all().delete()
        self.assertEqual(self.inicial(),(date(2026,10,21),date(2026,11,20)))


class ReferenciaIncidenciasTests(TestCase):
    def test_13_8_5_anclado_a_hasta_con_limites_locales_inclusivos(self):
        hasta=date(2026,8,20);fin=fecha(hasta+timedelta(days=1),0)
        dias=[1,5,10,20,30,31,45,60,61,70,80,89,90]
        for n,d in enumerate(dias,1):
            ODT.objects.create(numero=n,cuenta_completa='FIR-1',contratista='Prueba',
                estado_softguard='Finalizado',fecha_finalizacion=fin-timedelta(days=d),
                fecha_creacion=fin-timedelta(days=d,hours=24))
        # Después del filtro, un microsegundo antes de la ventana y otro contratista.
        for n,cierre,extras in [(20,fin,{}),(21,fin-timedelta(days=90,microseconds=1),{}),
            (22,fin-timedelta(days=1),{'contratista':'Otro'}),(23,fin-timedelta(days=1),{'estado_softguard':'Asignado'}),
            (24,fin-timedelta(days=1),{'cuenta_completa':'Otra'})]:
            datos=dict(cuenta_completa='FIR-1',contratista='Prueba',estado_softguard='Finalizado');datos.update(extras)
            ODT.objects.create(numero=n,fecha_finalizacion=cierre,**datos)
        for cargar in (con_indicadores_odt,cargar_metricas):
            o=list(cargar(ODT.objects.filter(numero=1),hasta=hasta.isoformat()))[0]
            self.assertEqual((o.cantidad_incidencias,o.cantidad_incidencias_60,o.cantidad_incidencias_30),(13,8,5))
            self.assertEqual(o.estado_sla,'CUMPLE')

    def test_incluye_hasta_a_las_2359_y_no_el_dia_siguiente(self):
        fin=fecha(date(2026,11,21),0)
        for n,cierre in ((1,fin-timedelta(microseconds=1)),(2,fin)):
            ODT.objects.create(numero=n,cuenta_completa='FIR-1',contratista='Prueba',estado_softguard='Finalizado',fecha_finalizacion=cierre)
        o=con_indicadores_odt(ODT.objects.filter(numero=1),hasta='2026-11-20').get()
        self.assertEqual(o.cantidad_incidencias,1)
        self.assertEqual(o.cantidad_incidencias_30,1)

    def test_sin_hasta_conserva_referencia_actual_y_hasta_invalido_no_falla(self):
        ahora=fecha(date(2026,11,25))
        ODT.objects.create(numero=1,cuenta_completa='FIR-1',contratista='Prueba',estado_softguard='Finalizado',fecha_finalizacion=ahora)
        with patch('revisiones.consultas.ventanas_incidencias.timezone.now',return_value=ahora):
            for hasta in (None,'','invalido','9999-12-31'):
                self.assertEqual(con_indicadores_odt(ODT.objects.all(),hasta=hasta).get().cantidad_incidencias,1)


class OrdenGlobalTests(TestCase):
    def setUp(self):
        self.usuario=User.objects.create_superuser('jiturriaga',password='test')
        for n in range(1,62):
            ODT.objects.create(numero=n,cuenta_completa=f'FIR-{n:03}',contratista=f'Contratista {n:03}',
                fecha_finalizacion=fecha(date(2026,11,1))+timedelta(hours=n),servicio=SERVICIOS_PRINCIPALES[0],
                estado_softguard='Finalizado')
        self.client.force_login(self.usuario)

    def pagina(self, orden, direccion='asc', pagina=1, queryset=None, **extras):
        return paginar_filas(queryset if queryset is not None else ODT.objects.all(),pagina,
            orden_seleccionado=orden,direccion=direccion,**extras)

    def test_cuatro_ordenes_sql_globales_en_ambas_direcciones(self):
        for orden in ('cuenta','numero','contratista','finalizacion'):
            for direccion in ('asc','desc'):
                with self.subTest(orden=orden,direccion=direccion):
                    esperado=list(range(1,62));esperado=esperado[::-1] if direccion=='desc' else esperado
                    actual=[o.numero for o in self.pagina(orden,direccion)]+[o.numero for o in self.pagina(orden,direccion,2)]
                    self.assertEqual(actual,esperado)

    def test_orden_explicito_supera_prioridad_correccion_pero_fdp_sigue_al_final(self):
        CorreccionODT.objects.create(odt=ODT.objects.get(numero=61),corrige_monto=True,monto_objetivo=1)
        ODT.objects.filter(numero=1).update(observaciones_insumos='fdp')
        qs,activo=marcar_fallos(ODT.objects.all(),self.usuario)
        primera=self.pagina('numero',queryset=qs,priorizar_fallos=activo)
        ultima=self.pagina('numero',pagina=2,queryset=qs,priorizar_fallos=activo)
        self.assertEqual([o.numero for o in primera],list(range(2,52)))
        self.assertEqual(ultima.object_list[-1].numero,1)
        self.assertEqual(self.pagina('',queryset=qs).object_list[0].numero,61)

    def test_coordinadores_se_ordenan_globalmente_por_nombre_no_por_pagina(self):
        def datos(ns):
            return {n:{'nombre':'Zeta' if n<=55 else 'Álvaro','disponible':True} for n in ns}
        primera=self.pagina('coordinador',resolver_coordinadores=datos)
        self.assertEqual([o.numero for o in primera][:6],list(range(56,62)))
        ultima=self.pagina('coordinador','desc',2,resolver_coordinadores=datos)
        self.assertEqual([o.numero for o in ultima][-6:],list(range(56,62)))

    def test_coordinador_no_disponible_va_al_final_y_no_amplia_alcance(self):
        def datos(ns):return {n:{'nombre':'A' if n==1 else 'Z','disponible':n!=1} for n in ns}
        p=self.pagina('coordinador',queryset=ODT.objects.filter(numero__lte=3),resolver_coordinadores=datos)
        self.assertEqual([o.numero for o in p],[2,3,1])
        self.assertEqual(p.paginator.count,3)

    def test_ancla_y_filas_guardadas_conservan_pagina_en_orden_coordinador(self):
        resolver=lambda ns:{n:{'nombre':'Mismo nombre'} for n in ns}
        p=self.pagina('coordinador',pagina=1,resolver_coordinadores=resolver,numero_ancla='61')
        self.assertEqual(p.number,2)
        p=self.pagina('coordinador',pagina=2,resolver_coordinadores=resolver,
            numero_ancla='61',filas_guardadas='61,60,999999')
        self.assertEqual([o.numero for o in p],[61,60])

    def test_nulos_de_fecha_quedan_al_final_en_ambos_sentidos(self):
        ODT.objects.filter(numero=1).update(fecha_finalizacion=None)
        for direccion in ('asc','desc'):
            p=self.pagina('finalizacion',direccion,2)
            self.assertEqual(p.object_list[-1].numero,1)

    def test_parametros_no_permitidos_no_entran_en_order_by(self):
        self.assertEqual(leer_orden(QueryDict('orden=revision__estado&direccion=DROP')),('','asc'))
        self.assertEqual(leer_orden(QueryDict('orden=numero&direccion=desc')),('numero','desc'))

    def test_vista_conserva_orden_fecha_y_url_de_exportacion(self):
        datos={'fecha_desde':'2026-11-01','fecha_hasta':'2026-11-20','orden':'numero','direccion':'desc','page':'2'}
        with patch('revisiones.vistas.bandeja.coordinadores_para_mostrar',side_effect=resolver):
            r=self.client.get(reverse('bandeja'),datos)
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.context['registros'][0].numero,11)
        q=parse_qs(r.context['querystring']);self.assertEqual(q['orden'],['numero']);self.assertEqual(q['direccion'],['desc'])
        self.assertEqual(parse_qs(urlsplit(r.context['url_consulta']).query)['page'],['2'])
        self.assertEqual(parse_qs(urlsplit(r.context['url_exportacion']).query)['fecha_hasta'],['2026-11-20'])
        self.assertContains(r,'name="orden"');self.assertContains(r,'2026-11-20, incluyendo el día completo')

    def test_fechas_manuales_no_consultan_estado_del_periodo(self):
        with patch('revisiones.consultas.periodo_bandeja.periodo_inicial') as inicial, \
             patch('revisiones.vistas.bandeja.coordinadores_para_mostrar',side_effect=resolver):
            r=self.client.get(reverse('bandeja'),{'fecha_desde':'','fecha_hasta':''})
        inicial.assert_not_called();self.assertEqual(r.context['filtros']['fecha_desde'],'')
        self.assertEqual(r.context['filtros']['fecha_hasta'],'')

    def test_exportacion_excel_respeta_el_orden_elegido(self):
        url=reverse('bandeja')+'?fecha_desde=2026-11-01&fecha_hasta=2026-11-20&orden=numero&direccion=desc'
        with patch('revisiones.acceso_coordinadores.coordinadores_para_mostrar',side_effect=resolver):
            r=self.client.post(url,{'exportar':'seleccion','seleccion':'1,2,61','formato':'xlsx'})
        self.assertEqual(r.status_code,200)
        ws=load_workbook(BytesIO(r.content)).active
        self.assertEqual([ws.cell(n,1).value for n in range(7,10)],[61,2,1])
