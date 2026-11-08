"""Adaptador HTTP de descarga: permisos, selección, validación y respuesta."""
from collections import OrderedDict
from datetime import date
from decimal import Decimal
from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from ..facturacion_models import PeriodoFacturacion, FacturacionContratista
from ..pdf.componentes import nombre_archivo_seguro
from ..consultas.exportacion_pdf import datos_contratista_pdf, items_facturados, odts_aprobadas
from ..casos_uso.exportacion_pdf import generar_pdf_contratista, generar_zip_facturacion

@login_required
@permission_required(
    "revisiones.exportar_pagos_sstt",
    raise_exception=True,
)
def exportar_aprobados_pdf(request):

    periodo_id = request.GET.get(
        "periodo",
        "",
    ).strip()

    historico = bool(periodo_id)

    # ========================================================
    # OPCIÓN 1: HISTORIAL DE FACTURACIÓN
    # GENERAR ZIP CON UN PDF POR CONTRATISTA
    # ========================================================

    if historico:

        if not periodo_id.isdigit():
            return HttpResponseBadRequest(
                "Período inválido."
            )

        periodo = get_object_or_404(
            PeriodoFacturacion,
            pk=int(periodo_id),
        )

        desde = periodo.fecha_desde
        hasta = periodo.fecha_hasta

        seleccion = None
        if request.GET.get("seleccion") == "1":
            valores = request.GET.getlist("facturacion")
            if not valores or any(not v.isdigit() for v in valores):
                return HttpResponseBadRequest("Selecciona al menos un contratista válido.")
            seleccion = {int(v) for v in valores}
            permitidos = set(FacturacionContratista.objects.filter(
                periodo=periodo, pk__in=seleccion
            ).values_list("pk", flat=True))
            if seleccion != permitidos:
                return HttpResponseBadRequest("La selección no corresponde al período.")
        items = items_facturados(periodo, seleccion)

        if not items:
            return HttpResponseBadRequest(
                "El período no tiene ODT facturadas."
            )

        # ----------------------------------------------------
        # AGRUPAR ODT POR CONTRATISTA
        # ----------------------------------------------------

        grupos = OrderedDict()
        requisiciones = {}

        for item in items:

            nombre = item.facturacion.contratista

            if nombre not in grupos:
                grupos[nombre] = []

            grupos[nombre].append((
                item.odt,
                item.servicio_facturado,
                (
                    item.monto_facturado
                    if item.monto_facturado is not None
                    else Decimal("0")
                ),
                nombre,
            ))

            requisiciones[nombre] = (
                item.facturacion.numero_requisicion
            )

        # ----------------------------------------------------
        # GENERAR UN PDF INDEPENDIENTE POR CONTRATISTA
        # ----------------------------------------------------

        try:
            contenido_zip = generar_zip_facturacion(
                grupos, requisiciones, desde, hasta,
                incluir_bancarios=request.user.has_perm("contratistas.ver_bancos_contratistas_sstt"),
                generar_pdf=generar_pdf_contratista, resolver_contratista=datos_contratista_pdf,
            )

        except Exception as error:
            # Evitar entregar un ZIP incompleto.
            return HttpResponse(
                (
                    "No fue posible generar todos los "
                    "reportes del período. "
                    f"Detalle: {error}"
                ),
                status=503,
                content_type=(
                    "text/plain; charset=utf-8"
                ),
            )

        # ----------------------------------------------------
        # DESCARGAR ZIP DEL PERÍODO
        # ----------------------------------------------------

        respuesta = HttpResponse(
            contenido_zip,
            content_type="application/zip",
        )

        respuesta["Content-Disposition"] = (
            'attachment; filename="'
            f"Facturacion_SSTT_{desde:%Y%m%d}_"
            f'{hasta:%Y%m%d}.zip"'
        )

        return respuesta

    # ========================================================
    # OPCIÓN 2: BANDEJA
    # MANTENER EXPORTACIÓN PDF INDIVIDUAL
    # ========================================================

    contratista = request.GET.get(
        "contratista",
        "",
    ).strip()

    desde_texto = request.GET.get(
        "fecha_desde",
        "",
    ).strip()

    hasta_texto = request.GET.get(
        "fecha_hasta",
        "",
    ).strip()

    if (
        not contratista
        or not desde_texto
        or not hasta_texto
    ):
        return HttpResponseBadRequest(
            "Selecciona un contratista y ambas "
            "fechas antes de exportar."
        )

    try:
        desde = date.fromisoformat(desde_texto)
        hasta = date.fromisoformat(hasta_texto)

    except ValueError:
        return HttpResponseBadRequest(
            "Las fechas no tienen un formato válido."
        )

    if desde > hasta:
        return HttpResponseBadRequest(
            "La fecha inicial no puede superar "
            "la fecha final."
        )

    # --------------------------------------------------------
    # OBTENER ODT APROBADAS
    # --------------------------------------------------------

    odts = odts_aprobadas(
        contratista, desde, hasta, estado=request.GET.get("estado", "").strip(),
        tipo_cliente=request.GET.get("tipo_cliente", "").strip(),
        servicios=request.GET.getlist("servicios"), q=request.GET.get("q", "").strip(),
    )

    if not odts:
        return HttpResponseBadRequest(
            "No existen ODT aprobadas para "
            "este contratista y período."
        )

    # --------------------------------------------------------
    # PREPARAR SERVICIOS Y MONTOS APROBADOS
    # --------------------------------------------------------

    detalles = []

    for odt in odts:

        servicio = (
            odt.servicio_editado
            if odt.servicio_editado is not None
            else odt.servicio
        )

        monto = (
            odt.valor_pago_editado
            if odt.valor_pago_editado is not None
            else (
                odt.valor_pago_tecnico
                or Decimal("0")
            )
        )

        detalles.append((
            odt,
            servicio,
            monto,
            odt.contratista,
        ))

    # --------------------------------------------------------
    # GENERAR UN ÚNICO PDF PARA LA BANDEJA
    # --------------------------------------------------------

    try:
        pdf_bytes = generar_pdf_contratista(
            nombre_contratista=contratista,
            registros_contratista=detalles,
            desde=desde,
            hasta=hasta,
            requisicion="",
            historico=False,
            datos_contratista=datos_contratista_pdf(contratista),
            incluir_bancarios=request.user.has_perm("contratistas.ver_bancos_contratistas_sstt"),
        )

    except Exception as error:
        return HttpResponse(
            (
                "No fue posible generar el PDF. "
                f"Detalle: {error}"
            ),
            status=503,
            content_type="text/plain; charset=utf-8",
        )

    respuesta = HttpResponse(
        pdf_bytes,
        content_type="application/pdf",
    )

    nombre_seguro = nombre_archivo_seguro(
        contratista
    )

    respuesta["Content-Disposition"] = (
        'attachment; filename="'
        f"Reporte_SSTT_{nombre_seguro}_"
        f"{desde:%Y%m%d}_"
        f'{hasta:%Y%m%d}.pdf"'
    )

    return respuesta

