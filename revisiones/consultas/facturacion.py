"""Selección común para previsualizar y confirmar, siempre con aprobación efectiva."""
from datetime import datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone

from ..models import ODT
from .pagos import condicion_aprobada


def odts_facturables(seleccion):
    inicio = timezone.make_aware(datetime.combine(seleccion.desde, time.min))
    fin = timezone.make_aware(datetime.combine(seleccion.hasta + timedelta(days=1), time.min))
    qs = ODT.objects.filter(
        fecha_finalizacion__gte=inicio, fecha_finalizacion__lt=fin,
        estado_softguard__iexact="Finalizado",
    ).filter(condicion_aprobada())
    if seleccion.contratistas_filtrados and not seleccion.contratistas:
        return qs.none()
    if seleccion.contratistas:
        qs = qs.filter(contratista__in=seleccion.contratistas)
    else:
        qs = qs.exclude(contratista="")
    if seleccion.servicios:
        qs = qs.filter(
            Q(servicio_editado__isnull=True, servicio__in=seleccion.servicios)
            | Q(servicio_editado__in=seleccion.servicios)
        )
    if seleccion.tipo_cliente:
        qs = qs.filter(tipo_cliente=seleccion.tipo_cliente)
    if seleccion.estado and seleccion.estado.lower() != "finalizado":
        return qs.none()
    if seleccion.q:
        q = seleccion.q
        condicion = (Q(contratista__icontains=q) | Q(tecnico__icontains=q)
                     | Q(cuenta_completa__icontains=q) | Q(servicio__icontains=q)
                     | Q(servicio_editado__icontains=q) | Q(direccion__icontains=q))
        if q.isascii() and q.isdigit() and len(q) <= 10:
            condicion |= Q(numero=int(q))
        qs = qs.filter(condicion)
    return qs.order_by("contratista", "numero")
