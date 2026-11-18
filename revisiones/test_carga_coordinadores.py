from datetime import date, datetime
from unittest.mock import patch
from django.contrib.auth.models import User
from django.http import QueryDict
from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.utils import timezone
from .consultas.carga_coordinadores import resumir_carga
from .coordinadores_softguard import CoordinadoresNoDisponibles
from .models import ODT, CorreccionODT, AsignacionCoordinadorODT
from .estadisticas_correcciones import estadisticas_correcciones


class CargaCoordinadoresTests(TestCase):
    def setUp(self):
        self.hoy=date(2026,11,18)
        self.admin=User.objects.create_superuser('admin',password='test')
        for n,estado,fecha in ((1,'Pendiente',datetime(2026,1,1)),
            (2,'Finalizado',datetime(2026,11,18,23,59,59)),(3,'Asignado',datetime(2026,6,1)),
            (4,'Marcha Blanca',datetime(2026,10,1)),(5,'',None),
            (6,'Finalizado',datetime(2025,12,31,23,59,59)),(7,'Asignado',datetime(2026,11,19))):
            ODT.objects.create(numero=n,estado_softguard=estado,contratista='Prueba',
                fecha_creacion=timezone.make_aware(fecha) if fecha else None)
        CorreccionODT.objects.create(odt=ODT.objects.get(numero=2),corrige_monto=True,monto_objetivo=2)
        ODT.objects.filter(numero=3).update(servicio_editado='Editado')
        self.datos={n:{'identificado':True,'usuario':'a' if n<3 else 'b',
                       'nombre':'Coordinador A' if n<3 else 'Coordinador B'} for n in range(1,8)}
        self.datos[4]={'identificado':False,'usuario':None}

    def resumen(self, parametros=None):
        return resumir_carga(ODT.objects.all(),parametros or QueryDict(),
            lambda numeros:{n:self.datos[n] for n in numeros},hoy=self.hoy)

    def contexto(self, **datos):
        req=RequestFactory().get('/',datos);req.user=self.admin
        with patch('revisiones.estadisticas_correcciones.timezone.localdate',return_value=self.hoy), \
             patch('revisiones.acceso_coordinadores.identificar_coordinadores_odt',side_effect=lambda ns:{n:self.datos[n] for n in ns}), \
             patch('revisiones.estadisticas_correcciones.render',side_effect=lambda r,t,c:c):
            return estadisticas_correcciones(req),req

    def test_total_incluye_con_y_sin_correcciones_todos_los_estados(self):
        carga=self.resumen()
        self.assertTrue(carga['disponible'])
        self.assertEqual((carga['cantidad'],carga['con_correcciones']),(4,2))
        self.assertEqual(sum(carga['totales_estados']),4)
        self.assertEqual(set(carga['estados']),{'Pendiente','Asignado','Finalizado','Marcha Blanca'})
        self.assertEqual(carga['filas'][0]['usuario'],'a')
        self.assertEqual(carga['filas'][0]['cantidad'],2)
        self.assertEqual(carga['filas'][0]['con_correcciones'],1)
        self.assertEqual(next(f for f in carga['filas'] if f['usuario']=='SIN_IDENTIFICAR')['cantidad'],1)

    def test_coordinador_filtra_total_pero_no_opciones(self):
        carga=self.resumen(QueryDict('coordinador=b'))
        self.assertEqual(carga['cantidad'],1)
        self.assertIn('a',carga['opciones'])
        self.assertEqual(self.resumen(QueryDict('coordinador=desconocido'))['cantidad'],0)
        self.assertEqual(self.resumen(QueryDict('coordinador=SIN_IDENTIFICAR'))['cantidad'],1)

    def test_limites_locales_inclusivos_y_todo_historico_explicito(self):
        carga=self.resumen(QueryDict('carga_desde=2026-11-18&carga_hasta=2026-11-18'))
        self.assertEqual(carga['cantidad'],1)
        carga=self.resumen(QueryDict('carga_desde=&carga_hasta='))
        self.assertEqual(carga['cantidad'],7)
        self.assertIn('Sin estado',carga['estados'])

    def test_fecha_invalida_o_invertida_no_amplia_la_consulta(self):
        for parametros in ('carga_desde=invalida','carga_desde=2026-12-01&carga_hasta=2026-01-01',
                           'carga_hasta=9999-12-31'):
            carga=self.resumen(QueryDict(parametros))
            self.assertFalse(carga['disponible'])
            self.assertTrue(carga['errores'])
            self.assertEqual(carga['cantidad'],0)

    def test_filtros_de_correcciones_no_reducen_carga(self):
        contexto,req=self.contexto(tipo='AMBOS',estado='ACTUALIZADA')
        self.assertEqual(contexto['total']['cantidad'],0)
        self.assertEqual(contexto['carga']['cantidad'],4)
        self.assertIn({'usuario':'b','nombre':'Coordinador B'},contexto['coordinadores'])
        # Las fechas solo afectan la carga; el seguimiento anterior se conserva.
        contexto,req=self.contexto(carga_desde='2026-01-01',carga_hasta='2026-01-01')
        self.assertEqual(contexto['carga']['cantidad'],1)
        self.assertEqual(contexto['total']['cantidad'],1)

    def test_fallo_de_origen_no_es_sin_identificar_ni_total_parcial(self):
        def fallo(ns):
            raise CoordinadoresNoDisponibles()
        carga=resumir_carga(ODT.objects.all(),QueryDict(),fallo,hoy=self.hoy)
        self.assertFalse(carga['disponible'])
        self.assertEqual(carga['filas'],[])
        self.assertIn('Total no disponible',carga['errores'][0])
        carga=resumir_carga(ODT.objects.all(),QueryDict(),lambda ns:{n:{'identificado':False,'disponible':False} for n in ns},hoy=self.hoy)
        self.assertFalse(carga['disponible'])

    def test_lotes_acotados_y_conteo_unico(self):
        ODT.objects.bulk_create([ODT(numero=n,fecha_creacion=timezone.make_aware(datetime(2026,6,1))) for n in range(10,511)])
        tamanos=[]
        def resolver(ns):
            tamanos.append(len(ns))
            return {n:{'identificado':True,'usuario':'a','nombre':'Coordinador A'} for n in ns}
        carga=resumir_carga(ODT.objects.all(),QueryDict(),resolver,hoy=self.hoy)
        self.assertEqual(tamanos,[250,250,5])
        self.assertEqual(carga['cantidad'],505)
        self.assertEqual(carga['con_correcciones'],2)

    def test_asignacion_manual_comparte_resolver_sin_sql(self):
        odt=ODT.objects.get(numero=1)
        AsignacionCoordinadorODT.objects.create(odt=odt,usuario_coordinador='jtapia',asignado_por=self.admin)
        req=RequestFactory().get('/');req.user=self.admin
        from .acceso_coordinadores import coordinadores_en_peticion
        with patch('revisiones.coordinadores_softguard.consultar_eventos_coordinadores') as sql:
            carga=resumir_carga(ODT.objects.filter(numero=1),QueryDict(),lambda ns:coordinadores_en_peticion(req,ns),hoy=self.hoy)
        sql.assert_not_called()
        self.assertEqual(carga['filas'][0]['usuario'],'jtapia')

    def test_plantilla_tabla_desplazable_fechas_y_enlaces_conservados(self):
        contexto,req=self.contexto(carga_desde='2026-01-01',carga_hasta='2026-11-18')
        from django.template.loader import render_to_string
        html=render_to_string('revisiones/estadisticas_correcciones.html',contexto,request=req)
        for texto in ('Total de ODT por coordinador','Con correcciones','Creación desde','Marcha Blanca',
                      'Sin coordinador identificado','data-scroll-superior','Detalle de ODT modificadas'):
            self.assertIn(texto,html)
        self.assertIn('carga_desde=2026-01-01&amp;carga_hasta=2026-11-18#detalle-odt-modificadas',html)
        self.assertEqual(ODT.objects.count(),7)
        self.assertEqual(CorreccionODT.objects.count(),1)

    def test_permiso_y_middleware_no_abren_analisis_a_coordinadores(self):
        usuario=User.objects.create_user('coordinadora')
        self.client.force_login(usuario)
        self.assertEqual(self.client.get(reverse('estadisticas_correcciones')).status_code,403)
        from django.contrib.auth.models import Group, Permission
        from django.contrib.contenttypes.models import ContentType
        grupo=Group.objects.create(name='Coordinador')
        permiso,_=Permission.objects.get_or_create(content_type=ContentType.objects.get_for_model(ODT),codename='ver_bandeja_sstt')
        grupo.permissions.add(permiso);usuario.groups.add(grupo)
        self.assertNotEqual(self.client.get(reverse('estadisticas_correcciones')).status_code,200)

    def test_lectura_proyectada_sin_consultas_por_fila(self):
        with self.assertNumQueries(1):
            carga=self.resumen()
        self.assertEqual(carga['cantidad'],4)

    def test_error_no_muestra_tabla_parcial_y_preserva_correcciones(self):
        contexto,req=self.contexto(carga_desde='invalida')
        self.assertEqual(contexto['total']['cantidad'],1)
        from django.template.loader import render_to_string
        html=render_to_string('revisiones/estadisticas_correcciones.html',contexto,request=req)
        self.assertIn('Total no disponible',html)
        self.assertEqual(html.count('data-tabla-desplazable'),2)
        self.assertIn('Detalle de ODT modificadas',html)
        contexto,req=self.contexto()
        html=render_to_string('revisiones/estadisticas_correcciones.html',contexto,request=req)
        self.assertEqual(html.count('data-tabla-desplazable'),3)

    def test_error_despues_de_un_lote_descarta_resultado_incompleto(self):
        ODT.objects.bulk_create([ODT(numero=n,fecha_creacion=timezone.make_aware(datetime(2026,6,1))) for n in range(10,511)])
        llamadas=[]
        def resolver(ns):
            llamadas.append(len(ns))
            if len(llamadas)>1:
                raise CoordinadoresNoDisponibles()
            return {n:{'identificado':True,'usuario':'a','nombre':'Coordinador A'} for n in ns}
        carga=resumir_carga(ODT.objects.all(),QueryDict(),resolver,hoy=self.hoy)
        self.assertFalse(carga['disponible'])
        self.assertEqual(carga['filas'],[])
        self.assertEqual(carga['cantidad'],0)
