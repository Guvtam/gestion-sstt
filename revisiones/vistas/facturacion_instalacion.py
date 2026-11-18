"""Historial común, con agregaciones limitadas a instantáneas autorizadas."""
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, render

from ..acceso_instalacion import limitar_instalacion, exigir_factura_completa
from ..consultas.resumen_facturacion import resumir_items
from ..facturacion_models import FacturacionODT, FacturacionContratista, PeriodoFacturacion


def historial_instalacion(request):
    items = limitar_instalacion(FacturacionODT.objects.select_related(
        'odt', 'facturacion', 'facturacion__periodo'), historico=True)
    # El filtro del JOIN limita también conteos y sumas de facturas mixtas.
    periodos = list(PeriodoFacturacion.objects.filter(facturaciones__items__in=items).annotate(
        cantidad_contratistas=Count('facturaciones', distinct=True),
        cantidad_odt=Count('facturaciones__items', distinct=True),
        monto_total=Sum('facturaciones__items__monto_facturado'),
    ).order_by('-fecha_hasta', '-id'))
    facturas = FacturacionContratista.objects.filter(items__in=items).select_related(
        'periodo', 'creado_por').annotate(cantidad_odt=Count('items'), monto_total=Sum('items__monto_facturado'))

    buscar_odt = request.GET.get('buscar_odt', '').strip()
    buscar_requisicion = request.GET.get('buscar_requisicion', '').strip()
    busqueda_activa = bool(buscar_odt or buscar_requisicion)
    numero = buscar_odt.replace(' ', '').replace('.', '')
    error_busqueda = ''
    numero_odt = None
    encontrados = items
    if numero:
        if numero.isascii() and numero.isdigit() and len(numero) <= 10:
            numero_odt = int(numero)
            encontrados = encontrados.filter(odt__numero=numero_odt)
        else:
            error_busqueda = 'Ingresa un número de ODT válido.'
            encontrados = encontrados.none()
    if buscar_requisicion:
        encontrados = encontrados.filter(facturacion__numero_requisicion__icontains=buscar_requisicion)

    periodo = None
    factura = None
    detalle = []
    resumen = None
    facturas_periodo = []
    periodo_id = request.GET.get('periodo', '').strip()
    factura_id = request.GET.get('contratista', '').strip()
    if periodo_id:
        validos = {str(p.pk): p for p in periodos}
        if periodo_id not in validos:
            from django.http import Http404
            raise Http404('Período no encontrado.')
        periodo = validos[periodo_id]
        items_periodo = items.filter(facturacion__periodo=periodo)
        encontrados = encontrados.filter(facturacion__periodo=periodo)
        resumen = resumir_items(items_periodo)
        # La vista restringida tiene una única categoría autorizada.
        resumen['categorias'] = {'nueva_instalacion': {
            'nombre':'Mantenimiento nueva instalación', 'cantidad':resumen['cantidad'], 'monto':resumen['total']}}
        facturas_periodo = list(facturas.filter(periodo=periodo).order_by('contratista'))
        for f in facturas_periodo:
            try:
                exigir_factura_completa(request.user, f)
                f.puede_editar_requisicion = True
            except PermissionDenied:
                f.puede_editar_requisicion = False
        if factura_id:
            if not factura_id.isascii() or not factura_id.isdigit() or len(factura_id)>10:
                from django.http import Http404
                raise Http404('Facturación no encontrada.')
            factura = get_object_or_404(facturas.filter(periodo=periodo), pk=int(factura_id))
            detalle = list(items_periodo.filter(facturacion=factura).order_by('odt__numero'))
            encontrados = encontrados.filter(facturacion=factura)

    parametros = request.GET.copy()
    parametros.pop('page_busqueda', None)
    resultados = None
    if busqueda_activa:
        resultados = Paginator(facturas.filter(pk__in=encontrados.values('facturacion_id')).order_by(
            '-periodo__fecha_hasta', 'contratista', 'pk'), 50).get_page(request.GET.get('page_busqueda'))
    return render(request, 'revisiones/historial_facturacion.html', {
        'facturacion_restringida':True,
        'periodos':periodos, 'periodo_seleccionado':periodo,
        'facturaciones':facturas_periodo, 'facturacion_seleccionada':factura,
        'detalle_odt':detalle, 'resumen_costos':resumen,
        'buscar_odt':buscar_odt, 'numero_odt_buscada':numero_odt,
        'buscar_requisicion':buscar_requisicion, 'busqueda_activa':busqueda_activa,
        'error_busqueda':error_busqueda, 'resultados_busqueda':resultados,
        'query_busqueda':parametros.urlencode(),
    })
