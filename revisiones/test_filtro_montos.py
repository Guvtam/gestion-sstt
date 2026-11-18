from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth.models import User
from django.http import QueryDict
from django.template.loader import render_to_string
from django.test import TestCase, RequestFactory, SimpleTestCase
from django.utils import timezone
from .dominio.filtros_montos import leer_montos
from .dominio.facturacion import SeleccionFacturacion, FacturacionInvalida
from .consultas.montos_bandeja import filtrar_montos, opciones_montos
from .consultas.facturacion import odts_facturables
from .consultas.exportacion_pdf import odts_aprobadas
from .casos_uso.facturacion import previsualizar, confirmar
from .models import ODT
from .vistas.bandeja import bandeja


class LecturaMontosTests(SimpleTestCase):
    def test_ausente_y_seleccion_vacia_son_distintos(self):
        self.assertEqual(leer_montos(QueryDict()), ((), False))
        self.assertEqual(leer_montos(QueryDict('montos_filtrados=1')), ((), True))

    def test_decimales_exactos_ordenados_sin_duplicados(self):
        self.assertEqual(leer_montos(QueryDict('monto=2&monto=0.00&monto=2.00&monto=25000.50')),
                         (('0.00', '2.00', '25000.50'), True))

    def test_invalidos_no_amplian_la_seleccion(self):
        for valor in ('NaN', 'Infinity', '1e9', '2.001', '1,00', '1000000000000', '<script>'):
            self.assertEqual(leer_montos(QueryDict('monto=' + valor)), ((), True))


class FiltroMontosTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_superuser('admin', password='test')
        self.fecha = timezone.make_aware(datetime(2026, 11, 5, 12))
        for numero, original, editado in ((1, 100, 0), (2, 0, 2), (3, 25000, None),
                                           (4, Decimal('25000.50'), None)):
            ODT.objects.create(numero=numero, cuenta_completa=f'FIR-{numero}', contratista='A',
                               fecha_finalizacion=self.fecha, fecha_creacion=self.fecha,
                               estado_softguard='Finalizado', servicio='MANTENCION CORRECTIVA CON COBRO',
                               valor_pago_tecnico=original, valor_pago_editado=editado)

    def contexto(self, **datos):
        request = RequestFactory().get('/', {'fecha_desde': '2026-10-21', 'fecha_hasta': '2026-11-20', **datos})
        request.user = self.usuario
        with patch('revisiones.vistas.bandeja.coordinadores_para_mostrar', side_effect=lambda r, numeros: {n: {'identificado':False} for n in numeros}), \
             patch('revisiones.vistas.bandeja.render', side_effect=lambda r,t,c:c):
            return bandeja(request), request

    def test_importe_editado_prevalece_incluso_cero(self):
        self.assertEqual(opciones_montos(ODT.objects.all()), ['0.00','2.00','25000.00','25000.50'])
        self.assertEqual(list(filtrar_montos(ODT.objects.all(), ('0.00','2.00'), True)
                              .order_by('numero').values_list('numero', flat=True)), [1,2])
        self.assertFalse(filtrar_montos(ODT.objects.all(), ('100.00',), True).exists())

    def test_ninguno_no_devuelve_todos(self):
        self.assertEqual(filtrar_montos(ODT.objects.all()).count(), 4)
        self.assertFalse(filtrar_montos(ODT.objects.all(), (), True).exists())

    def test_contexto_indicadores_paginacion_y_casillas(self):
        contexto, request = self.contexto(monto=['2.00','25000.50'], montos_filtrados='1')
        self.assertEqual({o.numero for o in contexto['registros']}, {2,4})
        self.assertEqual(contexto['total']['cantidad'], 2)
        self.assertEqual(contexto['aprobadas']['monto'], Decimal('25002.50'))
        self.assertEqual(contexto['montos_disponibles'], ['0.00','2.00','25000.00','25000.50'])
        parametros = QueryDict(contexto['querystring'])
        self.assertEqual(parametros.getlist('monto'), ['2.00','25000.50'])
        html = render_to_string('revisiones/bandeja.html', contexto, request=request)
        self.assertIn('name="monto" value="2.00" checked', html)
        self.assertIn('name="monto" value="0.00" >', html)

    def test_opciones_respetan_busqueda_y_alcance(self):
        contexto, _ = self.contexto(q='FIR-3')
        self.assertEqual(contexto['montos_disponibles'], ['25000.00'])
        with patch('revisiones.vistas.bandeja.es_coordinador_sstt', return_value=True), \
             patch('revisiones.vistas.bandeja.datos_coordinador', return_value={'usuario':'prueba'}), \
             patch('revisiones.vistas.bandeja.limitar_odts_coordinador', side_effect=lambda r,qs:qs.none()):
            contexto, _ = self.contexto()
        self.assertEqual(contexto['montos_disponibles'], [])
        self.assertEqual(contexto['total']['cantidad'], 0)

    def test_lista_no_se_limita_a_la_primera_pagina(self):
        ODT.objects.bulk_create([ODT(numero=n, cuenta_completa='FIR-X', contratista='A',
            fecha_finalizacion=self.fecha, estado_softguard='Finalizado', valor_pago_tecnico=100)
            for n in range(10, 65)])
        contexto, _ = self.contexto(monto=['100.00'], page='2')
        self.assertEqual(contexto['pagina'].number, 2)
        self.assertEqual(contexto['pagina'].paginator.count, 55)
        self.assertEqual(len(contexto['registros']), 5)

    def seleccion(self, **datos):
        return SeleccionFacturacion(date(2026,10,21), date(2026,11,20), contratistas=('A',), **datos)

    def test_facturacion_y_pdf_aplican_misma_seleccion(self):
        seleccion = self.seleccion(montos=('2.00',), montos_filtrados=True)
        self.assertEqual(list(odts_facturables(seleccion).values_list('numero',flat=True)), [2])
        pdf = odts_aprobadas('A', seleccion.desde, seleccion.hasta, montos=seleccion.montos,
                             montos_filtrados=True)
        self.assertEqual([o.numero for o in pdf], [2])
        self.assertFalse(odts_facturables(self.seleccion(montos_filtrados=True)).exists())
        self.assertEqual(odts_aprobadas('A',seleccion.desde,seleccion.hasta,montos_filtrados=True), [])

    def test_cambiar_montos_invalida_confirmacion(self):
        seleccion = self.seleccion(montos=('2.00',), montos_filtrados=True)
        vista = previsualizar(self.usuario, seleccion)
        with self.assertRaises(FacturacionInvalida):
            confirmar(self.usuario, self.seleccion(montos=('25000.00',),montos_filtrados=True),
                      requisiciones={'A':'REQ'}, confirmacion=vista.confirmacion)
        # La selección original sigue siendo válida y factura solo su ODT.
        confirmar(self.usuario, seleccion, requisiciones={'A':'REQ'}, confirmacion=vista.confirmacion)
        from .facturacion_models import FacturacionODT
        self.assertEqual(list(FacturacionODT.objects.values_list('odt__numero',flat=True)), [2])


class FiltroMontosJSTests(SimpleTestCase):
    def test_controles_y_envio_del_formulario(self):
        import shutil
        import subprocess
        from pathlib import Path
        if not shutil.which('node'):
            self.skipTest('Node no está instalado.')
        base = Path(__file__).parent
        resultado = subprocess.run([shutil.which('node'), str(base / 'pruebas_js/filtro_montos.cjs'),
            str(base / 'static/revisiones/filtro_montos.js')], capture_output=True, text=True, timeout=15)
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)
