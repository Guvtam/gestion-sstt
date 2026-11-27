from datetime import date
from io import BytesIO, StringIO
from unittest.mock import patch
from zipfile import ZipFile

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from pypdf import PdfReader

from revisiones.facturacion_models import PeriodoFacturacion, FacturacionContratista, FacturacionODT
from revisiones.models import ODT
from .models import Contratista, EquivalenciaSoftGuard


@override_settings(ROOT_URLCONF='config.urls')
class AccesoContratistasTests(TestCase):
    def setUp(self):
        call_command('configurar_perfiles', stdout=StringIO())
        self.usuario = get_user_model().objects.create_user('lector')
        self.c = Contratista.objects.create(nombre='Proveedor prueba', banco='Banco Prueba',
            numero_cuenta='000123456789', tipo_cuenta='Cuenta corriente')
        self.client.force_login(self.usuario)

    def test_consulta_completa_sin_permiso_bancario_ni_edicion(self):
        self.assertFalse(self.usuario.has_perm('contratistas.ver_bancos_contratistas_sstt'))
        r = self.client.get(reverse('contratistas:listado'))
        self.assertContains(r, 'Ver datos')
        self.assertNotContains(r, '+ Nuevo contratista')
        self.assertNotContains(r, '>Editar</a>')
        r = self.client.get(reverse('contratistas:detalle', args=[self.c.pk]))
        self.assertContains(r, 'Banco Prueba')
        self.assertContains(r, '000123456789')
        self.assertNotContains(r, '>Editar</a>')
        for nombre, args in [('editar', [self.c.pk]), ('nuevo', []),
                             ('equivalencias', [self.c.pk]), ('vinculacion_softguard', [])]:
            self.assertEqual(self.client.post(reverse('contratistas:' + nombre, args=args), {}).status_code, 403)
        self.assertEqual(Contratista.objects.count(), 1)

    def test_coordinador_y_calendario_pueden_consultar_sin_ampliar_edicion(self):
        grupo = Group.objects.get(name='Coordinador')
        self.usuario.groups.add(grupo)
        self.assertContains(self.client.get(reverse('contratistas:detalle', args=[self.c.pk])), 'Banco Prueba')
        self.assertContains(self.client.get(reverse('contratistas:listado')), 'Consultar contratistas')
        self.assertEqual(self.client.get(reverse('contratistas:editar', args=[self.c.pk])).status_code, 403)
        self.usuario.groups.clear()
        self.usuario.user_permissions.add(Permission.objects.get(codename='ver_calendario_sstt'))
        self.assertContains(self.client.get(reverse('contratistas:detalle', args=[self.c.pk])), '000123456789')

    def test_anonimo_no_consulta_datos(self):
        self.client.logout()
        for url in [reverse('contratistas:listado'), reverse('contratistas:detalle', args=[self.c.pk])]:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 302)
            self.assertNotIn(b'000123456789', r.content)

    def test_filtro_con_busqueda_y_vinculos_manuales(self):
        EquivalenciaSoftGuard.objects.create(contratista=self.c, nombre_softguard='T. EXTERNO - Prueba')
        manual = Contratista.objects.create(nombre='Proveedor manual', nombre_softguard='T. EXTERNO - Manual')
        pendiente = Contratista.objects.create(nombre='Proveedor pendiente', nombre_softguard='   ')
        r = self.client.get(reverse('contratistas:listado'), {'vinculacion': 'pendientes', 'q': 'Proveedor'})
        self.assertEqual([c.pk for c in r.context['pagina']], [pendiente.pk])
        r = self.client.get(reverse('contratistas:listado'), {'vinculacion': 'vinculados'})
        self.assertEqual({c.pk for c in r.context['pagina']}, {self.c.pk, manual.pk})
        self.assertEqual(EquivalenciaSoftGuard.objects.count(), 1)

    def test_paginacion_conserva_filtro(self):
        Contratista.objects.bulk_create([Contratista(nombre=f'Pendiente {i}') for i in range(31)])
        r = self.client.get(reverse('contratistas:listado'), {'vinculacion': 'pendientes', 'q': 'Pendiente'})
        self.assertContains(r, 'q=Pendiente&amp;vinculacion=pendientes&amp;page=2')
        self.assertEqual(r.context['pagina'].paginator.count, 31)

    def test_habilitar_juan_pablo_idempotente_sin_ampliar_otros_accesos(self):
        u = get_user_model().objects.create_user('jiturriaga')
        grupo = Group.objects.create(name='Perfil previo')
        u.groups.add(grupo)
        for _ in range(2):
            call_command('habilitar_administracion_contratistas', usuario='jiturriaga', stdout=StringIO())
        u = get_user_model().objects.get(pk=u.pk)
        self.assertTrue(u.has_perm('contratistas.gestionar_contratistas_sstt'))
        self.assertEqual(list(u.groups.all()), [grupo])
        self.assertEqual(u.user_permissions.count(), 1)
        self.assertFalse(u.is_staff)
        self.assertFalse(u.is_superuser)
        self.client.force_login(u)
        self.assertContains(self.client.get(reverse('contratistas:listado')), '+ Nuevo contratista')
        self.assertEqual(self.client.get(reverse('contratistas:editar', args=[self.c.pk])).status_code, 200)
        with self.assertRaises(CommandError):
            call_command('habilitar_administracion_contratistas', usuario='no_existe', stdout=StringIO())
        self.assertFalse(self.usuario.has_perm('contratistas.gestionar_contratistas_sstt'))

    def test_pdf_bandeja_e_historico_incluyen_banco_sin_permiso_especifico(self):
        self.usuario.user_permissions.add(Permission.objects.get(codename='exportar_pagos_sstt'))
        nombre = 'T. EXTERNO - Prueba'
        EquivalenciaSoftGuard.objects.create(contratista=self.c, nombre_softguard=nombre)
        odt = ODT.objects.create(numero=9001, contratista=nombre)
        periodo = PeriodoFacturacion.objects.create(fecha_desde=date(2026, 10, 21), fecha_hasta=date(2026, 11, 20))
        factura = FacturacionContratista.objects.create(periodo=periodo, contratista=nombre)
        FacturacionODT.objects.create(facturacion=factura, odt=odt, servicio_facturado='PREVENTIVO', monto_facturado=100)
        from revisiones.vistas.exportacion_pdf import exportar_aprobados_pdf
        from django.test import RequestFactory
        params = [{'contratista': nombre, 'fecha_desde': '2026-10-21', 'fecha_hasta': '2026-11-20'},
                  {'periodo': str(periodo.pk)}]
        for datos in params:
            request = RequestFactory().get('/', datos)
            request.user = get_user_model().objects.get(pk=self.usuario.pk)
            with patch('revisiones.casos_uso.exportacion_pdf.consultar_historial_odt', return_value=[]), \
                 patch('revisiones.vistas.exportacion_pdf.odts_aprobadas', return_value=[odt]):
                r = exportar_aprobados_pdf(request)
            self.assertEqual(r.status_code, 200)
            contenido = r.content
            if 'periodo' in datos:
                with ZipFile(BytesIO(contenido)) as z:
                    contenido = z.read(z.namelist()[0])
            texto = ''.join(p.extract_text() for p in PdfReader(BytesIO(contenido)).pages)
            self.assertIn('Banco Prueba', texto)
            self.assertIn('000123456789', texto)
            self.assertNotIn('Acceso restringido', texto)
