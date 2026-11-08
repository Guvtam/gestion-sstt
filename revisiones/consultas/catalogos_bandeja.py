"""Opciones auxiliares de bandeja, con la semántica previa de catálogo global."""
from django.db.models import Q
from ..models import ODT


def servicios_disponibles():
    originales = set(ODT.objects.exclude(servicio__isnull=True).exclude(servicio="")
                     .order_by().values_list("servicio", flat=True).distinct())
    editados = set(ODT.objects.exclude(servicio_editado__isnull=True).exclude(servicio_editado="")
                  .order_by().values_list("servicio_editado", flat=True).distinct())
    return sorted(originales | editados)


def estados_disponibles():
    return (ODT.objects.exclude(estado_softguard="").order_by("estado_softguard")
            .values_list("estado_softguard", flat=True).distinct())


def filtrar_opciones_ajax(registros, *, campo_fecha, fecha_desde="", fecha_hasta="",
                           estado="", servicios=()):
    """No autoriza alcance: el llamador debe aplicar la restricción del usuario."""
    if fecha_desde:
        registros = registros.filter(**{f"{campo_fecha}__date__gte": fecha_desde})
    if fecha_hasta:
        registros = registros.filter(**{f"{campo_fecha}__date__lte": fecha_hasta})
    if estado:
        registros = registros.filter(estado_softguard=estado)
    if servicios:
        registros = registros.filter(
            Q(servicio_editado__isnull=True, servicio__in=servicios)
            | Q(servicio_editado__in=servicios))
    return registros
