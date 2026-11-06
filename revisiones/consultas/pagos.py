"""Reglas SQL comunes a bandeja, previsualización y PDF."""
from django.db.models import DecimalField, Q
from django.db.models.functions import Coalesce

from ..dominio.pagos import ESTADOS_APROBADOS


def importe_efectivo():
    return Coalesce(
        "valor_pago_editado", "valor_pago_tecnico",
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )


def condicion_aprobada():
    """Sin revisión y POR_REVISAR se consideran aprobadas por regla vigente."""
    return Q(revision__isnull=True) | Q(revision__estado__in=ESTADOS_APROBADOS)
