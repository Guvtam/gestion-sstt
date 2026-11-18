"""Historial parcial basado en servicios congelados, incluso en facturas mixtas."""
from django.core.paginator import Paginator
from django.db.models import Sum
from django.shortcuts import render
from ..acceso_instalacion import limitar_instalacion, exigir_factura_completa
from django.core.exceptions import PermissionDenied
from ..facturacion_models import FacturacionODT


def historial_instalacion(request):
    items = limitar_instalacion(FacturacionODT.objects.select_related(
        'odt', 'facturacion', 'facturacion__periodo'), historico=True)
    numero = request.GET.get('buscar_odt', '').strip().replace(' ', '').replace('.', '')
    requisicion = request.GET.get('buscar_requisicion', '').strip()
    periodo = request.GET.get('periodo', '').strip()
    factura = request.GET.get('contratista', '').strip()
    if numero:
        items = items.filter(odt__numero=int(numero)) if numero.isascii() and numero.isdigit() and len(numero)<=10 else items.none()
    if requisicion:
        items = items.filter(facturacion__numero_requisicion__icontains=requisicion)
    for valor, campo in ((periodo, 'facturacion__periodo_id'), (factura, 'facturacion_id')):
        if valor:
            items = items.filter(**{campo:int(valor)}) if valor.isascii() and valor.isdigit() and len(valor)<=10 else items.none()
    total = items.aggregate(monto=Sum('monto_facturado'))['monto'] or 0
    parametros = request.GET.copy()
    parametros.pop('page', None)
    pagina = Paginator(items.order_by('-facturacion__periodo__fecha_hasta', 'facturacion_id', 'odt__numero'), 50).get_page(request.GET.get('page'))
    editables = {}
    for item in pagina.object_list:
        if item.facturacion_id not in editables:
            try:
                exigir_factura_completa(request.user, item.facturacion)
                editables[item.facturacion_id] = True
            except PermissionDenied:
                editables[item.facturacion_id] = False
        item.puede_editar_requisicion = editables[item.facturacion_id]
    return render(request, 'revisiones/historial_instalacion.html', {
        'pagina':pagina, 'page_obj':pagina, 'querystring':parametros.urlencode(),
        'monto_total':total, 'buscar_odt':request.GET.get('buscar_odt',''),
        'buscar_requisicion':requisicion,
    })
