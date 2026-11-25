from contextlib import closing
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from django.test import SimpleTestCase
from scripts.preparar_prueba_visual import copiar_base


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
