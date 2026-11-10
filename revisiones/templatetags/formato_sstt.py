"""Filtros de formato para la aplicación SSTT."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from django import template

register = template.Library()


@register.filter(name="tiempo_sla")
def tiempo_sla(value):
    """Presentar horas corridas; sobre 24 horas desglosar días, horas y minutos."""
    if value is None or value == "":
        return ""
    try:
        segundos = Decimal(str(value.total_seconds() if hasattr(value, "total_seconds") else value))
        if not segundos.is_finite() or segundos < 0:
            return ""
        minutos_totales = int(segundos // 60)
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        return ""
    horas, minutos = divmod(minutos_totales, 60)
    if segundos <= 86400:
        return f"{horas} h {minutos} min"
    dias, horas = divmod(horas, 24)
    texto = f"{dias} {'día' if dias == 1 else 'días'} {horas} h"
    return texto + (f" {minutos} min" if minutos else "")

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
