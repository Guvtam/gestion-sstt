"""Contrato de actualización del catálogo, sin HTTP ni acceso a datos."""
from dataclasses import dataclass


class CuentaInvalida(ValueError):
    pass


class CuentaNoEncontrada(LookupError):
    pass


@dataclass(frozen=True)
class CuentaActualizada:
    codigo: str
    odts_actualizadas: int


def validar_actualizacion(tipo, ceco, observaciones):
    tipo = str(tipo or "").strip()
    ceco = str(ceco or "").strip()
    observaciones = str(observaciones or "").strip()
    if tipo not in ("B2B", "B2C", "SIN_CLASIFICAR"):
        raise CuentaInvalida("La clasificación seleccionada no es válida.")
    if len(ceco) > 50:
        raise CuentaInvalida("El CECO no puede superar 50 caracteres.")
    return tipo, ceco, observaciones
