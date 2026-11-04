"""Filtros de formato para la aplicación SSTT."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from django import template

register = template.Library()

@register.filter(name="clp")
def clp(value):
    """Devuelve un monto entero CLP con puntos de miles, sin símbolo $."""
    if value is None or value == "":
        return "0"
    try:
        numero = Decimal(str(value))
        if not numero.is_finite():
            return "0"
        entero = int(numero.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError, TypeError):
        return "0"
    return format(entero, ",d").replace(",", ".")
