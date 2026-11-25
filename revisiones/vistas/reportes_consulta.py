"""Descargas de consulta: selección explícita y alcance validado en el servidor."""
from decimal import Decimal
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseBadRequest
from django.views.decorators.http import require_POST
from ..acceso_instalacion import limitar_pagos
from ..casos_uso.autorizacion import exigir_permiso_operativo
from ..dominio.pagos import estado_pago_efectivo
from ..dominio.servicios import servicio_efectivo
from ..facturacion_models import FacturacionODT
from ..pdf.reportes import pdf_reporte, xlsx_reporte, filtros_texto


def ids_seleccion(texto, limite=2000):
    valores=str(texto or '').split(',')
    if not 1<=len(valores)<=limite or any(not v.isascii() or not v.isdigit() or len(v)>10 or not 0<int(v)<=2147483647 for v in valores):
        raise ValueError(f'Selecciona entre 1 y {limite} registros válidos.')
    return sorted({int(v) for v in valores})


def moneda(valor):
    return '$ '+format(Decimal(str(valor or 0)),',.2f').replace(',','_').replace('.',',').replace('_','.')


def exportar_bandeja(request, registros, *, coordinador):
    exigir_permiso_operativo(request.user,'revisiones.exportar_pagos_sstt')
    if coordinador:raise PermissionDenied
    try:numeros=ids_seleccion(request.POST.get('seleccion'))
    except ValueError as e:return HttpResponseBadRequest(str(e))
    formato=request.POST.get('formato','')
    if formato not in ('pdf','xlsx'):return HttpResponseBadRequest('Formato no válido.')
    filas = list(registros.filter(numero__in=numeros).select_related('revision', 'seguimiento_correccion'))
    if {o.numero for o in filas} != set(numeros):
        return HttpResponseBadRequest('La selección contiene ODT fuera de los filtros o permisos vigentes. Actualiza o limpia la selección.')
    from ..acceso_coordinadores import coordinadores_para_mostrar
    from ..consultas.filas_bandeja import cargar_complementos
    from ..consultas.preventivos import asignar_ultimos_preventivos
    from ..presentacion.filas_bandeja import preparar_filas
    from ..templatetags.formato_sstt import tiempo_sla
    complementos = cargar_complementos(filas)
    preparar_filas(filas, coordinadores_pagina=coordinadores_para_mostrar(request, numeros),
        facturadas=complementos.facturadas, catalogo=complementos.catalogo,
        puede_procesar=False, puede_asignar=False)
    asignar_ultimos_preventivos(filas)
    cabeceras = ['ODT', 'Cuenta', 'Localidad', 'Técnico', 'Contratista', 'Servicio',
        'Observaciones', 'Coordinador', 'CECO', 'Tipo cliente', 'Creador ODT',
        'Creación', 'Finalización', 'Último preventivo', 'Incidencias 90 días',
        'Incidencias 60 días', 'Incidencias 30 días', 'SLA', 'Tiempo SLA',
        'Estado SoftGuard', 'Pago SoftGuard', 'Pago efectivo', 'Estado pago',
        'Estado de modificación', 'Informe']
    datos = []
    for o in filas:
        efectivo = o.valor_pago_editado if o.valor_pago_editado is not None else o.valor_pago_tecnico
        datos.append([o.numero, o.cuenta_completa, o.localidad, o.tecnico, o.contratista,
            servicio_efectivo(o.servicio, o.servicio_editado), o.observaciones_insumos,
            o.coordinador_nombre, 'Revisar CECO' if o.ceco_requiere_revision else o.ceco_catalogo,
            o.tipo_cliente_catalogo, o.usuario_creador, o.fecha_creacion, o.fecha_finalizacion,
            o.fecha_ultimo_preventivo, o.cantidad_incidencias, o.cantidad_incidencias_60,
            o.cantidad_incidencias_30, o.estado_sla, tiempo_sla(o.duracion_sla), o.estado_softguard,
            o.valor_pago_tecnico, efectivo,
            estado_pago_efectivo(o.revision.estado if hasattr(o, 'revision') else None),
            {'PENDIENTE':'Pendiente', 'EN_PROCESO':'Procesado', 'ACTUALIZADA':'Actualizado'}.get(o.estado_modificacion, 'Sin modificación'),
            o.get_estado_informe_display()])
    filtros = filtros_texto(request.GET) + f'; Selección: {len(datos)} ODT. Los importes son efectivos actuales, no una factura.'
    if formato == 'xlsx':
        return xlsx_reporte(cabeceras, datos, filtros)
    total_origen = sum((d[20] for d in datos), Decimal(0))
    total_efectivo = sum((d[21] for d in datos), Decimal(0))
    secciones = [
        ('ODT seleccionadas', ['ODT','Cuenta','Localidad','Técnico','Contratista','Servicio','Estado'],
         [[d[0],d[1],d[2],d[3],d[4],d[5],d[19]] for d in datos], [1,3,1.5,2,2,2,1]),
        ('Clasificación y responsables', ['ODT','Coordinador','CECO','Tipo cliente','Creador'],
         [[d[0],d[7],d[8],d[9],d[10]] for d in datos]),
        ('Fechas e indicadores', ['ODT','Creación','Finalización','Último preventivo','SLA','Tiempo SLA','90 días','60 días','30 días'],
         [[d[0],d[11],d[12],d[13],d[17],d[18],d[14],d[15],d[16]] for d in datos]),
        ('Importes y revisión', ['ODT','Pago SoftGuard','Pago efectivo','Estado pago','Modificación','Informe'],
         [[d[0],moneda(d[20]),moneda(d[21]),d[22],d[23],d[24]] for d in datos]),
        ('Observaciones', ['ODT','Observaciones SoftGuard'], [[d[0],d[6]] for d in datos], [1,8]),
        ('Totales de la selección', ['ODT','Monto SoftGuard','Monto efectivo'],
         [[len(datos),moneda(total_origen),moneda(total_efectivo)]])]
    return pdf_reporte('Órdenes de trabajo seleccionadas', secciones, filtros, 'ODT_seleccionadas.pdf')


@login_required
@permission_required('revisiones.exportar_pagos_sstt',raise_exception=True)
@require_POST
def informe_periodos_pdf(request):
    exigir_permiso_operativo(request.user,'revisiones.exportar_pagos_sstt')
    try:ids=ids_seleccion(request.POST.get('seleccion'),120)
    except ValueError as e:return HttpResponseBadRequest(str(e))
    items=limitar_pagos(request.user,FacturacionODT.objects.filter(facturacion__periodo_id__in=ids),historico=True)
    disponibles=set(items.values_list('facturacion__periodo_id',flat=True).distinct())
    if disponibles!=set(ids):raise PermissionDenied('Algún período no tiene facturación disponible para tu perfil.')
    if items.count()>10000:return HttpResponseBadRequest('Selecciona menos períodos: máximo 10.000 ODT por informe.')
    grupos={};detalle=[]
    for item in items.select_related('facturacion__periodo','odt').order_by('facturacion__periodo__fecha_desde','facturacion__contratista','odt__numero'):
        f=item.facturacion;p=f.periodo;etiqueta=f'{p.fecha_desde:%d/%m/%Y} al {p.fecha_hasta:%d/%m/%Y}'
        if p.pk not in grupos:grupos[p.pk]=[etiqueta,0,Decimal(0)]
        grupos[p.pk][1]+=1;grupos[p.pk][2]+=item.monto_facturado
        detalle.append([etiqueta,f.contratista,f.numero_requisicion,item.odt.numero,item.servicio_facturado,moneda(item.monto_facturado)])
    total=sum((g[2] for g in grupos.values()),Decimal(0))
    resumen=[[g[0],g[1],moneda(g[2])] for g in grupos.values()]+[['Total',len(detalle),moneda(total)]]
    return pdf_reporte('Informe de períodos facturados',[
        ('Resumen por período',['Período','ODT facturadas','Monto facturado'],resumen),
        ('Detalle histórico',['Período','Contratista facturado','Requisición','ODT','Servicio facturado','Monto facturado'],detalle)],
        'Selección explícita de períodos. Servicios e importes de la instantánea facturada; no se recalculan con valores actuales.',
        'Periodos_facturados.pdf')
