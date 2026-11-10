"""Lectura acotada de filas sobre un queryset previamente autorizado."""
from dataclasses import dataclass
from django.core.paginator import Paginator
from django.db.models import Case, When, Value, IntegerField, Q
from ..cuentas_utils import cargar_catalogo_cuentas
from ..facturacion_models import FacturacionODT
from .preventivos import asignar_ultimos_preventivos

TAMANO_PAGINA = 50
ORDEN_BANDEJA = ("cuenta_completa", "codigo_tecnico", "fecha_finalizacion", "-numero")


@dataclass(frozen=True)
class ComplementosFilas:
    facturadas: frozenset[int]
    catalogo: dict


def paginar_filas(registros, numero_pagina, numero_ancla=None, *, priorizar_correcciones=True):
    # Priorizar antes de paginar: no solo las correcciones de la página visible.
    # La ausencia de seguimiento conserva el estado pendiente de ediciones antiguas.
    pendientes = Q(seguimiento_correccion__estado="PENDIENTE") | (
        Q(seguimiento_correccion__isnull=True)
        & (Q(servicio_editado__isnull=False) | Q(valor_pago_editado__isnull=False))
    )
    orden = ORDEN_BANDEJA
    if priorizar_correcciones:
        registros = registros.alias(prioridad_correccion=Case(
            When(pendientes, then=Value(0)),
            When(seguimiento_correccion__estado="EN_PROCESO", then=Value(1)),
            default=Value(2), output_field=IntegerField(),
        ))
        orden = ("prioridad_correccion", *orden)
    # En ODT por creación una edición no debe mover la fila a otra página.
    ids = registros.order_by(*orden).values_list("pk", flat=True)
    # Buscar solo dentro del alcance autorizado y de los filtros vigentes.
    # Se recorre una proyección de IDs, sin cargar todas las ODT en memoria.
    ancla = str(numero_ancla or "")
    if ancla.isascii() and ancla.isdigit() and 0 < len(ancla) <= 10:
        pk_ancla = registros.filter(numero=int(ancla)).values_list("pk", flat=True).first()
        if pk_ancla is not None:
            for indice, pk in enumerate(ids.iterator(chunk_size=1000)):
                if pk == pk_ancla:
                    numero_pagina = indice // TAMANO_PAGINA + 1
                    break
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
