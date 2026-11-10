from pathlib import Path
import shutil
import subprocess
from unittest import skipUnless

from django.test import SimpleTestCase


@skipUnless(shutil.which("node"), "Node no está instalado para las pruebas JavaScript.")
class NavegacionJSTests(SimpleTestCase):
    def comprobar(self, nombre):
        base = Path(__file__).parent
        resultado = subprocess.run([
            shutil.which("node"), str(base / "pruebas_js" / (nombre+".cjs")),
            str(base / "static/revisiones" / (nombre+".js")),
        ], capture_output=True, text=True, timeout=15)
        self.assertEqual(resultado.returncode, 0, resultado.stdout+resultado.stderr)

    def test_volver_conserva_contexto_y_aisla_usuarios(self):
        self.comprobar("navegacion")

    def test_barras_sincronizadas_y_redimensionado(self):
        self.comprobar("tablas_desplazables")

    def test_desplegables_cierran_con_escape_clic_exterior_y_cambio_de_grupo(self):
        self.comprobar("menu_desplegable")
