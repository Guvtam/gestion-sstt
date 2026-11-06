
from django.contrib.auth.decorators import (
    login_required,
    permission_required,
)
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from .facturacion_models import (
    FacturacionContratista,
    FacturacionODT,
)
from .cuentas_utils import normalizar_codigo_cuenta, cargar_catalogo_cuentas, tipo_cliente_cuenta


@login_required
@permission_required(
    "revisiones.exportar_pagos_sstt",
    raise_exception=True,
)
@require_GET
def detalle_facturacion(request, facturacion_id):

    facturacion = get_object_or_404(
        FacturacionContratista.objects.select_related("periodo"),
        pk=facturacion_id,
    )

    items = list(
        FacturacionODT.objects
        .filter(facturacion=facturacion)
        .select_related("odt")
        .order_by("odt__numero")
    )

    catalogo = cargar_catalogo_cuentas(item.odt.cuenta_completa for item in items)

    # Asignar a cada ODT su clasificación real.
    for item in items:
        codigo = normalizar_codigo_cuenta(
            item.odt.cuenta_completa
        )

        cuenta = catalogo.get(codigo)

        item.odt.tipo_cliente_catalogo = tipo_cliente_cuenta(item.odt.cuenta_completa, catalogo)

        item.odt.ceco_catalogo = (
            cuenta.ceco if cuenta else ""
        )

    from .consultas.resumen_facturacion import resumir_items
    resumen = resumir_items(items, catalogo=catalogo)
    con_cobro = resumen["categorias"]["correctiva_con_cobro"]
    sin_cobro = resumen["categorias"]["correctiva_sin_cobro"]
    renovacion = resumen["categorias"]["renovacion"]
    preventivo = resumen["categorias"]["preventivo"]

    return render(
        request,
        "revisiones/detalle_facturacion.html",
        {
            "facturacion": facturacion,
            "items": items,
            "cantidad": len(items),
            "monto_total": resumen["total"],
            "cantidad_con_cobro": con_cobro["cantidad"],
            "monto_con_cobro": con_cobro["monto"],
            "cantidad_sin_cobro": sin_cobro["cantidad"],
            "monto_sin_cobro": sin_cobro["monto"],
            "cantidad_renovacion": renovacion["cantidad"],
            "monto_renovacion": renovacion["monto"],
            "cantidad_preventivo": preventivo["cantidad"],
            "monto_preventivo": preventivo["monto"],
        },
    )
