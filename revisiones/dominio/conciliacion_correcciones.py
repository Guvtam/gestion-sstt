"""Reglas de confirmación: $2 solicita informar un monto real en SoftGuard."""
from decimal import Decimal
from .servicios import normalizar_servicio

MARCA_MONTO = Decimal("2")


def servicio_confirmado(original, objetivo, corrige):
    return not corrige or normalizar_servicio(original) == normalizar_servicio(objetivo)


def monto_confirmado(original, objetivo, corrige):
    if not corrige:
        return True
    if objetivo == MARCA_MONTO:
        return original is not None and original > MARCA_MONTO
    return original == objetivo


def monto_seguimiento(odt, seguimiento):
    if not seguimiento.corrige_monto:
        return odt.valor_pago_tecnico
    if (seguimiento.monto_objetivo == MARCA_MONTO and seguimiento.estado == "ACTUALIZADA"
            and odt.valor_pago_editado is None):
        return odt.valor_pago_tecnico
    return seguimiento.monto_objetivo
