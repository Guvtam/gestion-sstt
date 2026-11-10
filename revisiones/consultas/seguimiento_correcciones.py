"""Lectura del seguimiento de correcciones, incluidas ediciones antiguas."""
from django.db.models import Case, CharField, Count, DecimalField, F, IntegerField, Q, Value, When
from django.db.models.functions import Coalesce

from ..models import ODT
from ..dominio.conciliacion_correcciones import MARCA_MONTO
from .pagos import importe_efectivo


def consultar_correcciones():
    return ODT.objects.select_related("revision", "seguimiento_correccion").filter(
        Q(seguimiento_correccion__isnull=False)
        | Q(servicio_editado__isnull=False) | Q(valor_pago_editado__isnull=False)
    ).annotate(
        estado_seguimiento=Coalesce("seguimiento_correccion__estado", Value("PENDIENTE"), output_field=CharField()),
        monto_objetivo_efectivo=Case(
            When(seguimiento_correccion__estado="ACTUALIZADA", seguimiento_correccion__monto_objetivo=MARCA_MONTO,
                 seguimiento_correccion__corrige_monto=True, valor_pago_editado__isnull=True, then=F("valor_pago_tecnico")),
            When(seguimiento_correccion__corrige_monto=True, then=F("seguimiento_correccion__monto_objetivo")),
            When(seguimiento_correccion__isnull=True, then=importe_efectivo()),
            default=F("valor_pago_tecnico"), output_field=DecimalField(max_digits=14, decimal_places=2),
        ),
    ).annotate(prioridad_seguimiento=Case(
        When(estado_seguimiento="PENDIENTE", then=Value(0)),
        When(estado_seguimiento="EN_PROCESO", then=Value(1)),
        default=Value(2), output_field=IntegerField(),
    )).order_by("prioridad_seguimiento", "-numero")


def filtrar_tipo(registros, tipo):
    monto = Q(seguimiento_correccion__corrige_monto=True) | Q(
        seguimiento_correccion__isnull=True, valor_pago_editado__isnull=False)
    servicio = Q(seguimiento_correccion__corrige_servicio=True) | Q(
        seguimiento_correccion__isnull=True, servicio_editado__isnull=False)
    if tipo == "MONTO":
        return registros.filter(monto)
    if tipo == "SERVICIO":
        return registros.filter(servicio)
    if tipo == "AMBOS":
        return registros.filter(monto & servicio)
    return registros


def contar_estados(registros):
    return registros.aggregate(
        total=Count("pk"),
        pendientes=Count("pk", filter=Q(estado_seguimiento="PENDIENTE")),
        procesadas=Count("pk", filter=Q(estado_seguimiento="EN_PROCESO")),
        actualizadas=Count("pk", filter=Q(estado_seguimiento="ACTUALIZADA")),
    )
