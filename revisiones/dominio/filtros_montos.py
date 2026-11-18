"""Selección exacta de importes, sin redondear ni aceptar números no finitos."""
from decimal import Decimal, InvalidOperation
import re


def leer_montos(parametros):
    explicitos = parametros.get("montos_filtrados") == "1" or "monto" in parametros
    return normalizar_montos(parametros.getlist("monto")), explicitos


def normalizar_montos(valores):
    montos = set()
    for valor in valores:
        texto = str(valor)
        if not re.fullmatch(r"-?[0-9]{1,12}(?:\.[0-9]{1,2})?", texto):
            continue
        try:
            montos.add(Decimal(texto))
        except InvalidOperation:
            continue
    return tuple(format(monto, ".2f") for monto in sorted(montos))
