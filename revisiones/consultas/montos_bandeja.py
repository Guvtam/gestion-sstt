"""Importes sobre consultas previamente autorizadas; no amplían su alcance."""
from .pagos import importe_efectivo


def filtrar_montos(registros, montos=(), explicitos=False):
    if not explicitos:
        return registros
    if not montos:
        return registros.none()
    return registros.alias(pago_filtrado=importe_efectivo()).filter(pago_filtrado__in=montos)


def opciones_montos(registros):
    valores = registros.order_by().annotate(pago_opcion=importe_efectivo()).values_list(
        "pago_opcion", flat=True).distinct().order_by("pago_opcion")
    return [format(valor, ".2f") for valor in valores]
