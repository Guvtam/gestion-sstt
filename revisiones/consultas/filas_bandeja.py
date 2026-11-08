"""Lectura acotada de filas sobre un queryset previamente autorizado."""
from dataclasses import dataclass
from django.core.paginator import Paginator
from ..cuentas_utils import cargar_catalogo_cuentas
from ..facturacion_models import FacturacionODT
from .preventivos import asignar_ultimos_preventivos

TAMANO_PAGINA = 50
ORDEN_BANDEJA = ("cuenta_completa", "codigo_tecnico", "fecha_finalizacion", "-numero")


@dataclass(frozen=True)
class ComplementosFilas:
    facturadas: frozenset[int]
    catalogo: dict


def paginar_filas(registros, numero_pagina):
    ids = registros.order_by(*ORDEN_BANDEJA).values_list("pk", flat=True)
    pagina = Paginator(ids, TAMANO_PAGINA).get_page(numero_pagina)
    ids_pagina = list(pagina.object_list)
    filas = list(registros.filter(pk__in=ids_pagina).select_related("revision", "seguimiento_correccion"))
    orden = {pk: posicion for posicion, pk in enumerate(ids_pagina)}
    filas.sort(key=lambda odt: orden[odt.pk])
    pagina.object_list = asignar_ultimos_preventivos(filas)
    return pagina


def cargar_complementos(filas):
    """Solo datos de las filas visibles; no vuelve a seleccionar ODT globalmente."""
    ids = [odt.pk for odt in filas]
    facturadas = frozenset(FacturacionODT.objects.filter(
        odt_id__in=ids).values_list("odt_id", flat=True))
    catalogo = cargar_catalogo_cuentas(odt.cuenta_completa for odt in filas)
    return ComplementosFilas(facturadas=facturadas, catalogo=catalogo)
