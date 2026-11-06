"""Estados vigentes: preservar la aprobación predeterminada del piloto."""
ESTADOS_APROBADOS = ("APROBADA", "POR_REVISAR")
OPCIONES_BANDEJA = (
    ("APROBADA", "Aprobado"),
    ("EN_REVISION", "En revisión"),
    ("RECHAZADA", "Rechazado"),
)


def estado_pago_efectivo(estado):
    return "APROBADA" if estado in (None, "POR_REVISAR") else estado


def motivo_bloqueo(*, facturada, rechazada):
    if facturada:
        return "La ODT ya está facturada y no permite modificaciones."
    if rechazada:
        return "La ODT está rechazada definitivamente y no permite modificaciones."
    return None
