"""Guardas estáticas de las capas extraídas; no ejecutan código del proyecto."""
import ast
from importlib.util import resolve_name
from pathlib import Path
from django.test import SimpleTestCase


class LimitesArquitecturaTests(SimpleTestCase):
    raiz=Path(__file__).resolve().parent

    def imports(self,ruta):
        paquete="revisiones."+str(ruta.relative_to(self.raiz).parent).replace("/",".")
        for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
            if isinstance(nodo,ast.Import):
                yield from (alias.name for alias in nodo.names)
            elif isinstance(nodo,ast.ImportFrom):
                modulo=resolve_name("."*nodo.level+(nodo.module or ""),paquete) if nodo.level else nodo.module or ""
                yield modulo
                yield from (modulo+"."+alias.name for alias in nodo.names)

    def test_dominio_y_presentacion_no_importan_http_orm_o_vistas(self):
        prohibidos=("django","revisiones.models","revisiones.facturacion_models",
                    "revisiones.views","revisiones.vistas")
        for carpeta in ("dominio","presentacion"):
            for ruta in (self.raiz/carpeta).glob("*.py"):
                with self.subTest(archivo=ruta.name):
                    self.assertFalse([m for m in self.imports(ruta)
                                      if any(m==p or m.startswith(p+".") for p in prohibidos)])

    def test_capas_extraidas_no_dependen_de_vistas(self):
        for carpeta in ("consultas","casos_uso","pdf","dominio","presentacion"):
            for ruta in (self.raiz/carpeta).glob("*.py"):
                with self.subTest(archivo=str(ruta.relative_to(self.raiz))):
                    self.assertFalse([m for m in self.imports(ruta)
                                      if m=="revisiones.views" or m.startswith("revisiones.views.")
                                      or m=="revisiones.vistas" or m.startswith("revisiones.vistas.")])

    def test_fachadas_de_compatibilidad_no_recuperan_logica(self):
        for nombre in ("views.py","exportar_pdf.py"):
            with self.subTest(archivo=nombre):
                nodos=ast.parse((self.raiz/nombre).read_text(encoding="utf-8")).body
                self.assertTrue(all(isinstance(n,(ast.Import,ast.ImportFrom))
                    or isinstance(n,ast.Expr) and isinstance(n.value,ast.Constant)
                    and isinstance(n.value.value,str) for n in nodos))
