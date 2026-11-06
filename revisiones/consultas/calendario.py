"""Selección común para calendario y conciliación de visitas."""
import calendar
from django.db.models.functions import Coalesce, Lower, Trim
from ..models import ODT


ESTADOS_VISITA = ("asignado", "pendiente", "en proceso", "finalizado")


def visitas_del_mes(mes):
    ultimo = mes.replace(day=calendar.monthrange(mes.year, mes.month)[1])
    return ODT.objects.annotate(
        estado_normalizado=Lower(Trim("estado_softguard")),
        servicio_efectivo=Coalesce("servicio_editado", "servicio"),
    ).filter(estado_normalizado__in=ESTADOS_VISITA,
             fecha_visita__range=(mes, ultimo))
