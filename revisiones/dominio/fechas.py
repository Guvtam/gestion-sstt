"""Operaciones de calendario compartidas."""
import calendar
from datetime import date


def sumar_meses(fecha, meses):
    indice = fecha.year * 12 + fecha.month - 1 + meses
    anio, mes = divmod(indice, 12)
    mes += 1
    return date(anio, mes, min(fecha.day, calendar.monthrange(anio, mes)[1]))
