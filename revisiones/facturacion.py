"""Adaptadores HTTP de facturación; las escrituras viven en casos de uso."""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from .casos_uso.facturacion import (
    actualizar_requisicion as guardar_requisicion,
    confirmar, previsualizar,
)
from .consultas.facturacion import odts_facturables
from .dominio.facturacion import (
    FacturacionInvalida, FacturacionNoEncontrada, SeleccionFacturacion, validar_periodo,
)
from .facturacion_models import FacturacionContratista, FacturacionODT


def _parametros(request):
    datos = request.GET if request.method == "GET" else request.POST
    try:
        desde = date.fromisoformat(datos.get("fecha_desde", ""))
        hasta = date.fromisoformat(datos.get("fecha_hasta", ""))
    except (ValueError, TypeError):
        raise FacturacionInvalida("Debes indicar ambas fechas válidas.") from None
    validar_periodo(desde, hasta)
    return desde, hasta, [v for v in datos.getlist("contratista") if v], [v for v in datos.getlist("servicios") if v], datos


def _seleccion(desde, hasta, contratistas, servicios, datos):
    return SeleccionFacturacion(
        desde=desde, hasta=hasta, contratistas=tuple(contratistas), servicios=tuple(servicios),
        contratistas_filtrados=datos.get("contratistas_filtrados") == "1",
        tipo_cliente=datos.get("tipo_cliente", ""), estado=datos.get("estado", ""), q=datos.get("q", ""),
    )


def _odts(desde, hasta, contratistas, servicios, datos):
    """Compatibilidad de la selección anterior, usando la consulta común."""
    return odts_facturables(_seleccion(desde, hasta, contratistas, servicios, datos))


def _resumen(qs):
    """Compatibilidad para consumidores que ya dispongan de un queryset."""
    grupos = defaultdict(lambda: {"cantidad": 0, "monto": Decimal("0")})
    for odt in qs.iterator(chunk_size=500):
        grupo = grupos[odt.contratista]
        grupo["cantidad"] += 1
        monto = odt.valor_pago_tecnico if odt.valor_pago_editado is None else odt.valor_pago_editado
        grupo["monto"] += monto if monto is not None else Decimal("0")
    return [{"contratista": nombre, **datos} for nombre, datos in sorted(grupos.items())]


@login_required
@permission_required("revisiones.exportar_pagos_sstt", raise_exception=True)
@require_http_methods(["GET", "POST"])
def previsualizar_facturacion(request):
    try:
        desde, hasta, contratistas, servicios, datos = _parametros(request)
        seleccion = _seleccion(desde, hasta, contratistas, servicios, datos)
        vista = previsualizar(request.user, seleccion)
    except ValueError as error:
        messages.error(request, str(error))
        return redirect("bandeja")

    resumen = vista.resumen
    ya_facturadas = FacturacionODT.objects.filter(odt__in=odts_facturables(seleccion)).count()
    existentes = {
        f.contratista: f.numero_requisicion for f in FacturacionContratista.objects.filter(
            periodo__fecha_desde=desde, periodo__fecha_hasta=hasta,
        )
    }
    for grupo in resumen:
        grupo["requisicion_existente"] = existentes.get(grupo["contratista"], "")

    if request.method == "POST":
        if not resumen:
            messages.error(request, "No existen ODT pendientes y aprobadas para facturar.")
        else:
            requisiciones = {grupo["contratista"]: datos.get(f"requisicion_{i}", "")
                             for i, grupo in enumerate(resumen)}
            try:
                resultado = confirmar(
                    request.user, seleccion, requisiciones=requisiciones,
                    confirmacion=datos.get("confirmacion_facturacion", ""),
                )
            except FacturacionInvalida as error:
                messages.error(request, f"No se guardó la facturación: {error}")
            else:
                messages.success(request,
                    f"Facturación guardada: {resultado.cantidad_odt} ODT de {resultado.cantidad_contratistas} contratistas.")
                return redirect(f"{reverse('historial_facturacion')}?periodo={resultado.periodo_id}")

    return render(request, "revisiones/facturacion_periodo.html", {
        "desde": desde, "hasta": hasta, "resumen": resumen,
        "cantidad_odt": vista.cantidad,
        "monto_total": sum((g["monto"] for g in resumen), Decimal("0")),
        "ya_facturadas": ya_facturadas, "confirmacion_facturacion": vista.confirmacion,
        "parametros": [(k, v) for k, valores in datos.lists() for v in valores
                       if k not in ("confirmacion_facturacion", "csrfmiddlewaretoken")
                       and not k.startswith("requisicion_")],
    })


@login_required
@permission_required("revisiones.exportar_pagos_sstt", raise_exception=True)
@require_POST
def actualizar_requisicion(request, facturacion_id):
    factura = get_object_or_404(FacturacionContratista, pk=facturacion_id)
    try:
        resultado = guardar_requisicion(
            request.user, facturacion_id=facturacion_id, numero=request.POST.get("numero_requisicion", ""),
        )
    except FacturacionInvalida as error:
        messages.error(request, str(error))
    except FacturacionNoEncontrada:
        raise Http404("Facturación no encontrada.") from None
    else:
        mensaje = (f"Requisición de {resultado.contratista} actualizada correctamente."
                   if resultado.numero else f"La requisición de {resultado.contratista} quedó pendiente.")
        messages.success(request, mensaje)
    return redirect(f"{reverse('historial_facturacion')}?periodo={factura.periodo_id}&contratista={factura.id}")


def resumen_costos_periodo(periodo):
    """Compatibilidad: esta vista conserva el mapa de montos por cliente."""
    from .consultas.resumen_facturacion import resumir_items
    resumen = resumir_items(
        FacturacionODT.objects.filter(facturacion__periodo=periodo).select_related("odt")
    )
    return {**resumen, "clientes": {
        tipo: datos["monto"] for tipo, datos in resumen["clientes"].items()
    }}
