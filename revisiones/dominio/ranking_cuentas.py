"""Ranking del período sobre las filas filtradas, sin acceso a bases de datos."""
from collections import Counter


def ranking_cuentas(filas, limite=50):
    cantidades = Counter()
    nombres = {}
    for odt in filas:
        clave = odt.clave_cuenta_analisis
        if not clave:
            continue
        cantidades[clave] += 1
        nombre = (odt.cuenta_completa or "").strip() or clave
        if nombre.upper().startswith(clave.upper()):
            nombre = nombre[len(clave):].lstrip(" -") or clave
        # Una cuenta puede tener nombres distintos entre ODT; etiqueta estable.
        if clave not in nombres or (nombre.casefold(), nombre) < (nombres[clave].casefold(), nombres[clave]):
            nombres[clave] = nombre
    ordenadas = sorted(cantidades, key=lambda clave: (-cantidades[clave], clave))[:limite]
    maximo = max(cantidades.values(), default=1)
    return [{"posicion": indice, "cuenta": clave, "nombre": nombres[clave],
             "cantidad": cantidades[clave], "ancho": f"{cantidades[clave] * 100 / maximo:.2f}"}
            for indice, clave in enumerate(ordenadas, 1)]
