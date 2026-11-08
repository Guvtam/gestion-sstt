"""Instrumentación temporal para comandos de diagnóstico en proceso independiente."""
from functools import wraps
from importlib import import_module
from time import perf_counter
from unittest.mock import patch


def instrumentar_etapas(stack, objetivos):
    """Rutas fijadas por código, nunca por entrada del usuario. Se restauran al salir."""
    resultados = {nombre: {"llamadas": 0, "segundos": 0.0, "fallos": 0} for nombre in objetivos}

    def envolver(funcion, nombre):
        @wraps(funcion)
        def medir(*args, **kwargs):
            resultado = resultados[nombre]
            resultado["llamadas"] += 1
            inicio = perf_counter()
            try:
                return funcion(*args, **kwargs)
            except Exception:
                resultado["fallos"] += 1
                raise
            finally:
                resultado["segundos"] += perf_counter() - inicio
        return medir

    for nombre, ruta in objetivos.items():
        modulo, atributo = ruta.rsplit(".", 1)
        objeto = import_module(modulo)
        stack.enter_context(patch.object(objeto, atributo, envolver(getattr(objeto, atributo), nombre)))
    return resultados
