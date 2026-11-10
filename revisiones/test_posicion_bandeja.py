from pathlib import Path
import shutil
import subprocess
from unittest import skipUnless

from django.test import SimpleTestCase


class PosicionBandejaJSTests(SimpleTestCase):
    @skipUnless(shutil.which("node"), "Node no está instalado para las pruebas JavaScript.")
    def test_guardado_retorno_filtros_y_almacenamiento_no_disponible(self):
        base = Path(__file__).parent
        resultado = subprocess.run([
            shutil.which("node"), str(base / "pruebas_js/posicion_bandeja.cjs"),
            str(base / "static/revisiones/posicion_bandeja.js"),
        ], capture_output=True, text=True, timeout=15)
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)
