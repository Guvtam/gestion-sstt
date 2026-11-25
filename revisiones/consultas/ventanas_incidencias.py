"""Ventanas móviles: fecha Hasta completa; sin Hasta se conserva el reloj actual."""
from datetime import date, datetime, time, timedelta
from django.utils import timezone


def referencia_incidencias(hasta=None):
    """Devuelve fin y operador: fecha válida => siguiente medianoche exclusiva."""
    try:
        dia = date.fromisoformat(hasta) if isinstance(hasta, str) and hasta else hasta
        if isinstance(dia, date) and not isinstance(dia, datetime):
            return timezone.make_aware(datetime.combine(dia + timedelta(days=1), time.min)), 'lt'
    except (ValueError, OverflowError):
        pass
    return timezone.now(), 'lte'
