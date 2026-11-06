"""Reglas SQL comunes a bandeja, previsualización y PDF."""
from django.db.models import DecimalField, Q
from django.db.models.functions import Coalesce

from ..dominio.pagos import ESTADOS_APROBADOS, motivo_bloqueo
from ..models import Revision
from ..facturacion_models import FacturacionODT


def importe_efectivo():
    return Coalesce(
        "valor_pago_editado", "valor_pago_tecnico",
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )


def condicion_aprobada():
    """Sin revisión y POR_REVISAR se consideran aprobadas por regla vigente."""
    return Q(revision__isnull=True) | Q(revision__estado__in=ESTADOS_APROBADOS)


def odt_facturada(odt):
    return FacturacionODT.objects.filter(odt=odt).exists()


def odt_rechazada(odt):
    return Revision.objects.filter(odt=odt, estado="RECHAZADA").exists()


def error_odt_bloqueada(odt):
    facturada = odt_facturada(odt)
    return motivo_bloqueo(facturada=facturada, rechazada=False if facturada else odt_rechazada(odt))
