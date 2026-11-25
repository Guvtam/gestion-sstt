from contextlib import closing
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from django.test import SimpleTestCase, TransactionTestCase
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from decimal import Decimal
from scripts.preparar_prueba_visual import copiar_base, preparar_esquema
from unittest.mock import patch
import sys


class CopiaVisualTests(SimpleTestCase):
    def test_copia_verificada_independiente_conserva_origen(self):
        with TemporaryDirectory() as d:
            origen=Path(d)/'origen.sqlite3';destino=Path(d)/'db_visual.sqlite3'
            with closing(sqlite3.connect(origen)) as c:
                c.execute('CREATE TABLE ejemplo (valor INTEGER)');c.execute('INSERT INTO ejemplo VALUES (123)');c.commit()
            copiar_base(origen,destino)
            with closing(sqlite3.connect(destino)) as c:
                self.assertEqual(c.execute('SELECT valor FROM ejemplo').fetchone()[0],123)
                c.execute('UPDATE ejemplo SET valor=0');c.commit()
            with closing(sqlite3.connect(origen)) as c:self.assertEqual(c.execute('SELECT valor FROM ejemplo').fetchone()[0],123)
            with self.assertRaises(ValueError):copiar_base(origen,destino)
            with self.assertRaises(ValueError):copiar_base(origen,origen)
            with self.assertRaises(ValueError):copiar_base(Path(d)/'inexistente.sqlite3',Path(d)/'nueva.sqlite3')
            self.assertFalse((Path(d)/'inexistente.sqlite3').exists())

    def test_migraciones_solo_sobre_copia_visual_explicita(self):
        with TemporaryDirectory() as d:
            destino=Path(d);(destino/'config').mkdir()
            with patch('scripts.preparar_prueba_visual.subprocess.run') as ejecutar:
                with self.assertRaises(ValueError):preparar_esquema(destino)
                ejecutar.assert_not_called()
                (destino/'config/settings_visual.py').touch()
                (destino/'db_visual.sqlite3').touch()
                preparar_esquema(destino)
            args,kwargs=ejecutar.call_args
            self.assertEqual(args[0],[sys.executable,str(destino/'manage.py'),'migrate','--noinput','--settings=config.settings_visual'])
            self.assertEqual(kwargs,{'cwd':destino,'check':True})



class EsquemaVisualAnteriorTests(TransactionTestCase):
    def test_actualiza_base_0015_sin_perder_odt_ni_ajustes(self):
        anteriores=[('revisiones','0015_proyeccioncoordinadorodt')]
        actuales=[('revisiones','0016_cambios_softguard')]
        executor=MigrationExecutor(connection)
        try:
            executor.migrate(anteriores)
            apps=executor.loader.project_state(anteriores).apps
            odt=apps.get_model('revisiones','ODT').objects.create(numero=987654,
                valor_pago_tecnico=Decimal('987.50'),valor_pago_editado=2,servicio_editado='SERVICIO CONSERVADO')
            self.assertNotIn('revisiones_cambiosoftguard',connection.introspection.table_names())
            executor=MigrationExecutor(connection);executor.migrate(actuales)
            apps=executor.loader.project_state(actuales).apps
            preservada=apps.get_model('revisiones','ODT').objects.get(pk=odt.pk)
            self.assertEqual(preservada.valor_pago_tecnico,Decimal('987.50'))
            self.assertEqual(preservada.valor_pago_editado,Decimal('2'))
            self.assertEqual(preservada.servicio_editado,'SERVICIO CONSERVADO')
            self.assertIn('revisiones_cambiosoftguard',connection.introspection.table_names())
            self.assertEqual(apps.get_model('revisiones','CambioSoftGuard').objects.count(),0)
        finally:
            executor=MigrationExecutor(connection);executor.migrate(executor.loader.graph.leaf_nodes())
