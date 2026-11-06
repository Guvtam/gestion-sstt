"""Carga y comprobación de bloqueos; llamar dentro de transaction.atomic()."""
from ..dominio.errores import ODTBloqueada, ODTNoEncontrada
from ..dominio.pagos import motivo_bloqueo
from ..facturacion_models import FacturacionODT
from ..models import ODT, Revision


def cargar_odts_editables(numeros):
    odts = list(ODT.objects.select_for_update().filter(numero__in=numeros).order_by("numero"))
    if len(odts) != len(numeros):
        raise ODTNoEncontrada("Algunas ODT seleccionadas no existen.")
    revisiones = Revision.objects.select_for_update().in_bulk([o.pk for o in odts], field_name="odt_id")
    facturadas = set(FacturacionODT.objects.filter(odt__in=odts).values_list("odt_id", flat=True))
    for odt in odts:
        revision = revisiones.get(odt.pk)
        bloqueo = motivo_bloqueo(
            facturada=odt.pk in facturadas, rechazada=revision is not None and revision.estado == "RECHAZADA",
        )
        if bloqueo:
            raise ODTBloqueada(f"ODT {odt.numero}: {bloqueo}" if len(numeros) > 1 else bloqueo)
    return odts, revisiones
