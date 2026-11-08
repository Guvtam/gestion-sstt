"""Contrato de gestión manual; Actualizada se determina por comparación con el origen."""
from dataclasses import dataclass
from .errores import DatosODTInvalidos
from .validacion_odt import texto


@dataclass(frozen=True)
class CorreccionGestionada:
    estado: str
    cambio: bool


def estado_gestion(estado, *, coordinador):
    estado = texto(estado)
    if coordinador and estado != "EN_PROCESO":
        raise DatosODTInvalidos("Solo puedes marcar la modificación como Procesada.")
    if estado not in ("PENDIENTE", "EN_PROCESO"):
        raise DatosODTInvalidos("Estado manual no permitido")
    return estado
