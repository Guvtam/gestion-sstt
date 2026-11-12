from datetime import datetime
import json
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError

from django.contrib.auth.models import User, Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core import signing
from django.test import TestCase, SimpleTestCase, override_settings, Client
from django.urls import reverse
from django.utils import timezone

from .casos_uso.analisis_cuenta_ia import preparar, seleccionar
from .dominio.analisis_cuenta_ia import AnalisisNoDisponible, depurar_texto, validar_resultado
from .integraciones.ia_cuentas import solicitar_analisis, leer_historiales
from .models import ODT
from .vistas.analisis_cuenta_ia import puede_analizar, SALT

EVENTOS = [{'NumeroODT':1,'FechaHora':datetime(2026,11,1,12),
            'Accion':'Observación','Observacion':'Se reemplazó batería. Correo: prueba@example.cl'}]


class PreparacionIA(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('admin', password='prueba')
        self.client.force_login(self.user)
        ct = ContentType.objects.get_for_model(ODT)
        for codigo in ('ver_bandeja_sstt','revisar_pago_sstt','ver_historial_sstt'):
            Permission.objects.get_or_create(content_type=ct,codename=codigo,defaults={'name':codigo})
        for n,cuenta in ((1,'FIR-3302 - CLIENTE PRIVADO CALLE 123'),(2,'FIR-33020 - Otra cuenta')):
            ODT.objects.create(numero=n, cuenta_completa=cuenta, servicio='MANTENIMIENTO PREVENTIVO',
                tecnico='Técnico privado', valor_pago_tecnico=50000, estado_softguard='Finalizado',
                observaciones_insumos='Falla batería <img src="https://firma/privada"> usuario@example.cl',
                fecha_finalizacion=timezone.make_aware(datetime(2026,11,1,12)))
        self.hist = patch('revisiones.casos_uso.analisis_cuenta_ia.leer_historiales',return_value=EVENTOS)
        self.mock_hist = self.hist.start()
        self.addCleanup(self.hist.stop)
        self.url = reverse('analisis_cuenta_ia')
        self.datos = {'codigo':'FIR-3302','desde':'2026-01-01','hasta':'2026-11-12','accion':'preparar'}

    def test_cuenta_exacta_datos_minimos_y_cobertura(self):
        preparada = preparar('FIR-3302','2026-01-01','2026-11-12')
        self.assertEqual(preparada['cantidad'],1)
        self.assertEqual(preparada['con_historial'],1)
        self.assertEqual(preparada['eventos'],1)
        self.mock_hist.assert_called_once_with([1])
        datos = json.dumps(preparada['datos'])
        for prohibido in ('CLIENTE PRIVADO','CALLE','Técnico privado','50000','example.cl','firma/privada'):
            self.assertNotIn(prohibido,datos)
        self.assertIn('1-E1',datos)

    def test_get_y_preparar_no_envian_a_ia(self):
        with patch('revisiones.vistas.analisis_cuenta_ia.solicitar_analisis') as api:
            self.assertEqual(self.client.get(self.url).status_code,200)
            self.mock_hist.assert_not_called()
            r = self.client.post(self.url,self.datos)
            self.assertContains(r,'Envío a IA desactivado')
            self.assertContains(r,'1 ODT')
            api.assert_not_called()
        self.assertEqual(ODT.objects.get(numero=1).valor_pago_tecnico,50000)

    def test_fechas_y_limites(self):
        for desde,hasta in (('mal','2026-01-01'),('2026-12-01','2026-01-01'),('2024-01-01','2026-01-01')):
            with self.assertRaises(AnalisisNoDisponible):seleccionar('FIR-3302',desde,hasta)
        with self.assertRaises(AnalisisNoDisponible):seleccionar('FIR-3302 OR 1=1','2026-01-01','2026-11-12')
        ODT.objects.bulk_create([ODT(numero=n, cuenta_completa='FIR-3302 - Cuenta', estado_softguard='Finalizado',
            fecha_finalizacion=timezone.make_aware(datetime(2026,11,1,12))) for n in range(3,104)])
        with self.assertRaises(AnalisisNoDisponible):preparar('FIR-3302','2026-01-01','2026-11-12')
        self.mock_hist.assert_not_called()

    def test_fallo_historial_no_es_cobertura_vacia(self):
        self.mock_hist.side_effect=AnalisisNoDisponible('Sin conexión')
        with patch('revisiones.vistas.analisis_cuenta_ia.solicitar_analisis') as api:
            r=self.client.post(self.url,self.datos)
            self.assertContains(r,'Sin conexión')
            self.assertNotIn('vista_previa',r.context)
            api.assert_not_called()

    def test_historial_vacio_y_evento_ajeno(self):
        self.mock_hist.return_value=[]
        self.assertEqual(preparar('FIR-3302','2026-01-01','2026-11-12')['con_historial'],0)
        self.mock_hist.return_value=[{**EVENTOS[0],'NumeroODT':2}]
        with self.assertRaises(AnalisisNoDisponible):preparar('FIR-3302','2026-01-01','2026-11-12')

    def test_permisos_piloto_y_csrf(self):
        self.assertTrue(puede_analizar(self.user))
        for grupo in ('Coordinador','Calendario de visitas','Gerente'):
            u=User.objects.create_user('usuario'+grupo.replace(' ',''))
            u.groups.add(Group.objects.get_or_create(name=grupo)[0])
            u.user_permissions.set(Permission.objects.filter(codename__in=['ver_bandeja_sstt','revisar_pago_sstt','ver_historial_sstt']))
            self.assertFalse(puede_analizar(u))
        supervisor=User.objects.create_user('supervisor')
        supervisor.groups.add(Group.objects.get_or_create(name='Supervisor')[0])
        self.assertFalse(puede_analizar(supervisor))
        supervisor.user_permissions.set(Permission.objects.filter(codename__in=['ver_bandeja_sstt','revisar_pago_sstt','ver_historial_sstt']))
        supervisor=User.objects.get(pk=supervisor.pk)
        self.assertTrue(puede_analizar(supervisor))
        c=Client(enforce_csrf_checks=True);c.force_login(self.user)
        self.assertEqual(c.post(self.url,self.datos).status_code,403)
        self.client.logout();self.assertEqual(self.client.get(self.url).status_code,302)

    @override_settings(SSTT_IA_HABILITADA=True,SSTT_OPENAI_API_KEY='prueba-no-real',
                       SSTT_OPENAI_MODEL='modelo-prueba',SECRET_KEY='clave-ficticia-para-pruebas-'*3,DEBUG=False)
    def test_envio_confirmado_revalida_fuentes_y_rechaza_cambios(self):
        self.client.force_login(self.user)
        previa=self.client.post(self.url,self.datos)
        token=previa.context['confirmacion']
        datos={**self.datos,'accion':'analizar','confirmar_envio':'SI','confirmacion':token}
        respuesta={'hallazgos':[{'tipo':'resumen','descripcion':'Se documenta reemplazo de batería.','referencias':['1-E1']}]}
        with patch('revisiones.vistas.analisis_cuenta_ia.solicitar_analisis',return_value=respuesta) as api:
            r=self.client.post(self.url,datos)
            self.assertContains(r,'Se documenta reemplazo')
            self.assertContains(r,'btn-historial-odt')
            self.assertEqual(api.call_count,1)
            self.assertEqual(ODT.objects.get(numero=1).valor_pago_tecnico,50000)
            api.reset_mock()
            for alterada in ({**datos,'confirmar_envio':''},{**datos,'codigo':'FIR-33020'},
                             {**datos,'confirmacion':'invalida'}):
                self.client.post(self.url,alterada)
                api.assert_not_called()
            ODT.objects.filter(numero=1).update(observaciones_insumos='Cambio posterior')
            r=self.client.post(self.url,datos)
            self.assertContains(r,'antecedentes cambiaron')
            api.assert_not_called()

    @override_settings(SSTT_IA_HABILITADA=False)
    def test_deshabilitado_impide_envio(self):
        with patch('revisiones.vistas.analisis_cuenta_ia.solicitar_analisis') as api:
            self.client.post(self.url,{**self.datos,'accion':'analizar','confirmar_envio':'SI'})
            api.assert_not_called()


class ReglasYProveedorIA(SimpleTestCase):
    def test_texto_sin_html_imagenes_contactos_y_limites(self):
        t=depurar_texto('<script>secreto</script><p>Batería</p><img src="data:image/png;base64,XXX"> a@b.cl +56 9 1234 5678 Firma en conformidad: Nombre privado')
        self.assertIn('Batería',t)
        for v in ('secreto','XXX','a@b.cl','1234','Nombre privado','<p>'):self.assertNotIn(v,t)
        self.assertIn('[texto recortado]',depurar_texto('x'*4000))

    def test_citas_ajenas_y_respuesta_invalida(self):
        datos={'odts':[{'numero':1,'fuentes':[{'id':'1-E1','texto':'Se reemplaza batería'}]}]}
        bueno={'hallazgos':[{'tipo':'resumen','descripcion':'Reemplazo registrado','referencias':['1-E1']}]}
        self.assertEqual(validar_resultado(bueno,datos)[0]['evidencias'][0]['numero'],1)
        for refs in ([],['2-E1'],[1]):
            with self.assertRaises(AnalisisNoDisponible):validar_resultado({'hallazgos':[{**bueno['hallazgos'][0],'referencias':refs}]},datos)
        for r in ({}, {'hallazgos':[]}, {'hallazgos':'mal'}):
            with self.assertRaises(AnalisisNoDisponible):validar_resultado(r,datos)

    @patch('revisiones.integraciones.ia_cuentas.build_opener')
    def test_api_formato_store_false_sin_herramientas_errores_y_rechazos(self,opener):
        respuesta={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'{"hallazgos":[]}'}]}]}
        opener.return_value.open.return_value.__enter__.return_value.read.return_value=json.dumps(respuesta).encode()
        self.assertEqual(solicitar_analisis({'odts':[]},clave='clave-ficticia',modelo='modelo-prueba'),{'hallazgos':[]})
        req=opener.return_value.open.call_args.args[0]
        carga=json.loads(req.data)
        self.assertFalse(carga['store']);self.assertNotIn('tools',carga)
        self.assertEqual(carga['text']['format']['type'],'json_schema')
        self.assertNotIn('clave-ficticia',json.dumps(carga))
        opener.return_value.open.side_effect=HTTPError(req.full_url,401,'secreto-del-proveedor',{},None)
        with self.assertRaises(AnalisisNoDisponible) as e:solicitar_analisis({},clave='x',modelo='y')
        self.assertNotIn('secreto-del-proveedor',str(e.exception))
        opener.return_value.open.side_effect=None
        opener.return_value.open.return_value.__enter__.return_value.read.return_value=b'{"status":"incomplete","output":[]}'
        with self.assertRaises(AnalisisNoDisponible):solicitar_analisis({},clave='x',modelo='y')

    @patch('revisiones.servicios_sql.obtener_conexion_sql')
    def test_sql_un_lote_parametrizado_y_cierre(self,conexion):
        cursor=conexion.return_value.cursor.return_value
        cursor.fetchmany.return_value=[(1,datetime(2026,1,1),'Observación','Falla')]
        self.assertEqual(leer_historiales([1])[0]['NumeroODT'],1)
        args=cursor.execute.call_args.args
        self.assertIn('IN (?)',args[0]);self.assertEqual(args[1],1)
        conexion.return_value.close.assert_called_once()
        cursor.fetchmany.side_effect=Exception('PASSWORD SECRETA')
        with self.assertRaises(AnalisisNoDisponible) as e:leer_historiales([1])
        self.assertNotIn('PASSWORD',str(e.exception))

class SintesisEjecutivaIA(SimpleTestCase):
    def setUp(self):
        self.datos={'odts':[{'numero':1,'fuentes':[{'id':'1-E1','texto':'Se realiza capacitación'}]}]}
        self.h={'tipo':'resumen','descripcion':'Hay demanda operativa documentada.','referencias':['1-E1']}

    def test_requiere_resumen_y_limita_extension_evidencias_y_repeticiones(self):
        buena=validar_resultado({'hallazgos':[self.h]},self.datos)
        self.assertEqual(buena[0]['titulo'],'Por qué se concentran las atenciones')
        casos=[{'hallazgos':[{**self.h,'tipo':'solucion'}]},
               {'hallazgos':[self.h]*9}, {'hallazgos':[self.h,self.h]},
               {'hallazgos':[{**self.h,'descripcion':'x'*1001}]},
               {'hallazgos':[{**self.h,'referencias':['1-E1']*5}]}]
        for caso in casos:
            with self.assertRaises(AnalisisNoDisponible):validar_resultado(caso,self.datos)

    def test_demanda_operativa_y_pendiente_son_categorias_distintas_de_solucion(self):
        salida=validar_resultado({'hallazgos':[self.h,
            {'tipo':'motivo','descripcion':'Se solicita capacitación recurrente.','referencias':['1-E1']},
            {'tipo':'pendiente','descripcion':'Se debe verificar disponibilidad de medios.','referencias':['1-E1']} ]},self.datos)
        self.assertEqual([s['tipo'] for s in salida],['resumen','motivo','pendiente'])
        self.assertEqual(salida[-1]['titulo'],'Pendientes y barreras')

    def test_una_firma_o_correo_omitido_no_son_evidencia_tecnica(self):
        for texto in ('', '[firma omitida]', '[[correo omitido]] [firma omitida]'):
            datos={'odts':[{'numero':1,'fuentes':[{'id':'1-E1','texto':texto}]}]}
            with self.assertRaises(AnalisisNoDisponible):validar_resultado({'hallazgos':[self.h]},datos)
