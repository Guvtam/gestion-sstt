
from decimal import Decimal

from django.contrib.auth.decorators import (
    login_required,
    permission_required,
)
from django.db.models import Sum
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from .facturacion_models import (
    FacturacionContratista,
    FacturacionODT,
)
from .models import CatalogoCuenta
from .cuentas_utils import normalizar_codigo_cuenta


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

    # Obtener los códigos de cuenta de las ODT facturadas.
    # Se utiliza la misma normalización que en la bandeja.
    codigos = {
        normalizar_codigo_cuenta(item.odt.cuenta_completa)
        for item in items
    }
    codigos.discard("")

    # Consultar el catálogo una sola vez.
    catalogo = {
        cuenta.codigo_cuenta: cuenta
        for cuenta in CatalogoCuenta.objects.filter(
            codigo_cuenta__in=codigos
        )
    }

    # Asignar a cada ODT su clasificación real.
    for item in items:
        codigo = normalizar_codigo_cuenta(
            item.odt.cuenta_completa
        )

        cuenta = catalogo.get(codigo)

        item.odt.tipo_cliente_catalogo = (
            cuenta.tipo_cliente
            if cuenta
            else "SIN_CLASIFICAR"
        )

        item.odt.ceco_catalogo = (
            cuenta.ceco if cuenta else ""
        )

    monto_total = sum(
        (
            item.monto_facturado or Decimal("0")
            for item in items
        ),
        Decimal("0"),
    )
    
# =====================================================
# RESUMEN POR TIPO DE SERVICIO FACTURADO
# =====================================================

    def normalizar_servicio(valor):
        return " ".join(
            str(valor or "").upper().split()
        ).replace("Ó", "O").replace("Á", "A").replace(
            "É", "E"
        ).replace("Í", "I").replace("Ú", "U")


    cantidad_con_cobro = 0
    monto_con_cobro = Decimal("0")

    cantidad_sin_cobro = 0
    monto_sin_cobro = Decimal("0")

    cantidad_renovacion = 0
    monto_renovacion = Decimal("0")
    cantidad_preventivo = 0
    monto_preventivo = Decimal("0")

    for item in items:
        servicio = normalizar_servicio(
            item.servicio_facturado
        )

        monto = item.monto_facturado or Decimal("0")

        if servicio == "MANTENCION CORRECTIVA CON COBRO":
            cantidad_con_cobro += 1
            monto_con_cobro += monto

        elif servicio == "MANTENCION CORRECTIVA SIN COBRO":
            cantidad_sin_cobro += 1
            monto_sin_cobro += monto

        elif servicio in ("MANTENIMIENTO RENOVACION", "MANTENCION RENOVACION", "RENOVACION"):
            cantidad_renovacion += 1
            monto_renovacion += monto

        elif servicio in ("MANTENIMIENTO PREVENTIVO", "MANTENCION PREVENTIVA", "PREVENTIVO"):
            cantidad_preventivo += 1
            monto_preventivo += monto


    return render(
        request,
        "revisiones/detalle_facturacion.html",
        {
            "facturacion": facturacion,
            "items": items,
            "cantidad": len(items),
            "monto_total": monto_total,
            "cantidad_con_cobro": cantidad_con_cobro,
            "monto_con_cobro": monto_con_cobro,
            "cantidad_sin_cobro": cantidad_sin_cobro,
            "monto_sin_cobro": monto_sin_cobro,
            "cantidad_renovacion": cantidad_renovacion,
            "monto_renovacion": monto_renovacion,
            "cantidad_preventivo": cantidad_preventivo,
            "monto_preventivo": monto_preventivo,
        },
    )
