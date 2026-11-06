"""Consulta paginada de auditoría, incluso si la cabecera ya no existe."""
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .casos_uso.autorizacion import exigir_permiso_operativo
from .facturacion_models import EventoRequisicion, FacturacionContratista


@login_required
@permission_required("revisiones.exportar_pagos_sstt", raise_exception=True)
@require_GET
def historial_requisiciones(request, facturacion_id):
    exigir_permiso_operativo(request.user, "revisiones.exportar_pagos_sstt")
    factura = FacturacionContratista.objects.select_related("periodo").filter(pk=facturacion_id).first()
    eventos = EventoRequisicion.objects.filter(facturacion_identificador=facturacion_id)
    ultimo = eventos.first()
    if factura is None and ultimo is None:
        raise Http404("Facturación no encontrada.")
    return render(request, "revisiones/historial_requisiciones.html", {
        "factura": factura, "ultimo": ultimo, "facturacion_id": facturacion_id,
        "contratista": factura.contratista if factura else ultimo.contratista,
        "desde": factura.periodo.fecha_desde if factura else ultimo.fecha_desde,
        "hasta": factura.periodo.fecha_hasta if factura else ultimo.fecha_hasta,
        "actual": factura.numero_requisicion if factura else ultimo.numero_nuevo,
        "pagina": Paginator(eventos, 50).get_page(request.GET.get("page")),
    })
