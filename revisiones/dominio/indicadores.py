"""SLA vigente: horas corridas, con fechas inválidas fuera del denominador."""
from datetime import timedelta

LIMITE_SLA = timedelta(hours=48)


def estado_sla(creacion, finalizacion):
    if creacion is None:
        return "SIN_DATOS"
    if finalizacion is None:
        return "PENDIENTE"
    duracion = finalizacion - creacion
    if duracion < timedelta(0):
        return "ERROR_FECHAS"
    return "CUMPLE" if duracion <= LIMITE_SLA else "NO_CUMPLE"
