
from decimal import Decimal

from django.contrib.auth.decorators import (
    login_required,
    permission_required,
)
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from .facturacion_models import (
    PeriodoFacturacion,
    FacturacionContratista,
    FacturacionODT,
)
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.shortcuts import redirect
from django.views.decorators.http import require_POST



def resumen_costos_periodo(periodo):
    """
    Calcula el resumen financiero de las ODT
    efectivamente facturadas en un período.
    """

    categorias = {
        "correctiva_con_cobro": {
            "nombre": "Mantención correctiva con cobro",
            "monto": Decimal("0"),
            "cantidad": 0,
        },
        "correctiva_sin_cobro": {
            "nombre": "Mantención correctiva sin cobro",
            "monto": Decimal("0"),
            "cantidad": 0,
        },
        "renovacion": {
            "nombre": "Mantención renovación",
            "monto": Decimal("0"),
            "cantidad": 0,
        },
        "preventivo": {
            "nombre": "Mantenimiento preventivo",
            "monto": Decimal("0"),
            "cantidad": 0,
        },
        "otros": {
            "nombre": "Otros servicios",
            "monto": Decimal("0"),
            "cantidad": 0,
        },
    }

    clientes = {
        "B2B": {
            "monto": Decimal("0"),
            "cantidad": 0,
            "promedio": Decimal("0"),
        },
        "B2C": {
            "monto": Decimal("0"),
            "cantidad": 0,
            "promedio": Decimal("0"),
        },
        "SIN_CLASIFICAR": {
            "monto": Decimal("0"),
            "cantidad": 0,
            "promedio": Decimal("0"),
        },
    }

    items = (
        FacturacionODT.objects
        .filter(facturacion__periodo=periodo)
        .select_related("odt")
    )

    total = Decimal("0")
    cantidad = 0

    for item in items.iterator(chunk_size=1000):

        monto = item.monto_facturado or Decimal("0")

        servicio = (
            item.servicio_facturado or ""
        ).strip().upper()

        servicio = (
            servicio
            .replace("Á", "A")
            .replace("É", "E")
            .replace("Í", "I")
            .replace("Ó", "O")
            .replace("Ú", "U")
        )

        if servicio == "MANTENCION CORRECTIVA CON COBRO":
            categoria = "correctiva_con_cobro"

        elif servicio == "MANTENCION CORRECTIVA SIN COBRO":
            categoria = "correctiva_sin_cobro"

        elif servicio in (
            "MANTENIMIENTO RENOVACION",
            "MANTENCION RENOVACION",
            "RENOVACION",
        ):
            categoria = "renovacion"

        elif servicio == "MANTENIMIENTO PREVENTIVO":
            categoria = "preventivo"

        else:
            categoria = "otros"

        categorias[categoria]["monto"] += monto
        categorias[categoria]["cantidad"] += 1
        

        tipo_cliente = (
            item.odt.tipo_cliente or ""
        ).strip().upper()

        if tipo_cliente not in ("B2B", "B2C"):
            tipo_cliente = "SIN_CLASIFICAR"

        clientes[tipo_cliente]["monto"] += monto
        clientes[tipo_cliente]["cantidad"] += 1

        total += monto
        cantidad += 1

        for datos in clientes.values():
            if datos["cantidad"] > 0:
                datos["promedio"] = (
                    datos["monto"] / datos["cantidad"]
                )

    return {
        "categorias": categorias,
        "clientes": clientes,
        "total": total,
        "cantidad": cantidad,
    }

@login_required
@permission_required(
    "revisiones.exportar_pagos_sstt",
    raise_exception=True
)
@require_GET
def historial_facturacion(request):

    # ==================================================
    # PERÍODOS DE FACTURACIÓN REGISTRADOS
    # ==================================================

    periodos = list(
        PeriodoFacturacion.objects.annotate(
            cantidad_contratistas=Count(
                "facturaciones",
                distinct=True,
            ),
            cantidad_odt=Count(
                "facturaciones__items",
                distinct=True,
            ),
            monto_total=Sum(
                "facturaciones__items__monto_facturado",
            ),
        ).order_by("-fecha_hasta", "-id")
    )

    for periodo in periodos:
        periodo.monto_total = (
            periodo.monto_total or Decimal("0")
        )

    # ==================================================
    # IDENTIFICAR PERÍODO SELECCIONADO
    # ==================================================

    periodo_id = request.GET.get(
        "periodo", ""
    ).strip()

    periodo_seleccionado = None
    facturaciones = []
    detalle_odt = []
    facturacion_seleccionada = None
    resumen_costos = None

    # ==================================================
    # CARGAR INFORMACIÓN DEL PERÍODO
    # ==================================================

    if periodo_id:

        periodo_seleccionado = get_object_or_404(
            PeriodoFacturacion,
            pk=periodo_id,
        )

        # ==============================================
        # RESUMEN DE COSTOS DEL PERÍODO
        # ==============================================

        resumen_costos = resumen_costos_periodo(
            periodo_seleccionado
        )

        # ==============================================
        # CONTRATISTAS DEL PERÍODO
        # ==============================================

        facturaciones = list(
            FacturacionContratista.objects.filter(
                periodo=periodo_seleccionado,
            )
            .select_related("creado_por")
            .annotate(
                cantidad_odt=Count("items"),
                monto_total=Sum(
                    "items__monto_facturado"
                ),
            )
            .order_by("contratista")
        )

        for facturacion in facturaciones:
            facturacion.monto_total = (
                facturacion.monto_total
                or Decimal("0")
            )

        # ==============================================
        # CONTRATISTA SELECCIONADO
        # ==============================================

        contratista_id = request.GET.get(
            "contratista", ""
        ).strip()

        if contratista_id:

            facturacion_seleccionada = (
                get_object_or_404(
                    FacturacionContratista,
                    pk=contratista_id,
                    periodo=periodo_seleccionado,
                )
            )

            # ==========================================
            # DETALLE DE ODT FACTURADAS
            # ==========================================

            detalle_odt = list(
                FacturacionODT.objects.filter(
                    facturacion=facturacion_seleccionada,
                )
                .select_related("odt")
                .order_by("odt__numero")
            )

    # ==================================================
    # RENDERIZAR HISTORIAL DE FACTURACIÓN
    # ==================================================

    return render(
        request,
        "revisiones/historial_facturacion.html",
        {
            "periodos": periodos,

            "periodo_seleccionado": (
                periodo_seleccionado
            ),

            "facturaciones": facturaciones,

            "facturacion_seleccionada": (
                facturacion_seleccionada
            ),

            "detalle_odt": detalle_odt,

            # Resumen financiero del período
            "resumen_costos": resumen_costos,
        },
    )




@login_required
@staff_member_required
@require_POST
def eliminar_periodo_facturacion(request, periodo_id):

    motivo = request.POST.get("motivo", "").strip()
    confirmacion = request.POST.get("confirmacion", "").strip()

    if not motivo:
        messages.error(
            request,
            "Debes indicar el motivo de eliminación."
        )
        return redirect("historial_facturacion")

    if confirmacion != "ELIMINAR":
        messages.error(
            request,
            "Debes confirmar la eliminación escribiendo ELIMINAR."
        )
        return redirect("historial_facturacion")

    with transaction.atomic():

        periodo = get_object_or_404(
            PeriodoFacturacion.objects.select_for_update(),
            pk=periodo_id,
        )

        nombre_periodo = str(periodo)

        facturaciones = FacturacionContratista.objects.filter(
            periodo=periodo
        )

        ids_facturaciones = list(
            facturaciones.values_list("pk", flat=True)
        )

        cantidad_odt = FacturacionODT.objects.filter(
            facturacion_id__in=ids_facturaciones
        ).count()

        cantidad_contratistas = len(ids_facturaciones)

        # 1. Eliminar asociaciones de ODT facturadas.
        FacturacionODT.objects.filter(
            facturacion_id__in=ids_facturaciones
        ).delete()

        # 2. Eliminar facturaciones de contratistas.
        facturaciones.delete()

        # 3. Eliminar el período.
        periodo.delete()

    messages.success(
        request,
        (
            f"Período {nombre_periodo} eliminado correctamente. "
            f"Se liberaron {cantidad_odt} ODT y "
            f"se eliminaron {cantidad_contratistas} "
            f"facturaciones de contratistas."
        )
    )

    return redirect("historial_facturacion")