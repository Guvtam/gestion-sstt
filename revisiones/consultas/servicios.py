"""Expresiones SQL de lectura: respetan el valor editado, incluso vacío."""
from django.db.models import Value
from django.db.models.functions import Coalesce, Replace, Trim, Upper


def servicio_normalizado():
    expresion = Trim(Coalesce("servicio_editado", "servicio"))
    # Traducir antes de Upper para cubrir tildes minúsculas incluso en SQLite.
    for original, destino in zip("áéíóúÁÉÍÓÚ", "aeiouAEIOU"):
        expresion = Replace(expresion, Value(original), Value(destino))
    return Upper(expresion)
