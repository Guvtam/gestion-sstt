"""Validación de entradas compartida por operaciones de ODT."""
from decimal import Decimal, InvalidOperation
import re

from .errores import DatosODTInvalidos
from .pagos import OPCIONES_BANDEJA


def numero_odt(valor, *, formateado=False):
    texto = str(valor if valor is not None else "").strip()
    if formateado:
        if not re.fullmatch(r"[0-9]+(?:[ .][0-9]{3})*", texto):
            raise DatosODTInvalidos("Número de ODT inválido.")
        texto = texto.replace(" ", "").replace(".", "")
    if not texto.isascii() or not texto.isdigit() or len(texto) > 10:
        raise DatosODTInvalidos("Número de ODT inválido.")
    numero = int(texto)
    if not 0 < numero <= 2147483647:
        raise DatosODTInvalidos("Número de ODT inválido.")
    return numero


def texto(valor):
    return str(valor if valor is not None else "").strip()


def estado_revision(estado, comentario):
    estado, comentario = texto(estado), texto(comentario)
    if estado not in dict(OPCIONES_BANDEJA):
        raise DatosODTInvalidos("Estado de revisión inválido.")
    if estado in ("EN_REVISION", "RECHAZADA") and not comentario:
        raise DatosODTInvalidos("Debes indicar el motivo para cambiar a En revisión o Rechazada.")
    return estado, comentario


def importe_pago(valor):
    try:
        importe = Decimal(texto(valor))
        if (not importe.is_finite() or importe < 0
                or importe > Decimal("999999999999.99") or importe.as_tuple().exponent < -2):
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        raise DatosODTInvalidos(
            "Monto inválido. Utiliza un valor no negativo con máximo 2 decimales."
        ) from None
    return importe


def servicio_obligatorio(valor):
    servicio = texto(valor)
    if not servicio or len(servicio) > 150:
        raise DatosODTInvalidos("El servicio es obligatorio y admite máximo 150 caracteres.")
    return servicio
