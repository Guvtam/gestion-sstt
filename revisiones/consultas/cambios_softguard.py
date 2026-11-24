"""Consulta independiente de detecciones en Seguimiento de cambios."""
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo
from django.core.paginator import Paginator
from ..models import CambioSoftGuard


def consultar_detecciones(parametros):
    consulta = CambioSoftGuard.objects.select_related('odt', 'ejecucion')
    errores = []
    valores = {k: parametros.get(k, '').strip() for k in ('sg_desde','sg_hasta','sg_odt','sg_campo')}
    fechas = {}
    for clave in ('sg_desde','sg_hasta'):
        if valores[clave]:
            try:
                fecha = date.fromisoformat(valores[clave])
                if fecha.year > 9998: raise ValueError
                fechas[clave] = fecha
            except ValueError:
                errores.append('Fecha de detección inválida.')
    if len(fechas) == 2 and fechas['sg_desde'] > fechas['sg_hasta']:
        errores.append('La fecha desde no puede ser posterior a hasta.')
    zona = ZoneInfo('America/Santiago')
    if 'sg_desde' in fechas:
        consulta = consulta.filter(detectado_en__gte=datetime.combine(fechas['sg_desde'],time.min,zona))
    if 'sg_hasta' in fechas:
        consulta = consulta.filter(detectado_en__lt=datetime.combine(fechas['sg_hasta']+timedelta(days=1),time.min,zona))
    if valores['sg_odt']:
        numero = valores['sg_odt'].replace(' ', '').replace('.', '')
        if not numero.isascii() or not numero.isdigit() or len(numero)>10 or int(numero)<1:
            errores.append('Número de ODT inválido.')
        else:
            consulta = consulta.filter(odt__numero=int(numero))
    if valores['sg_campo']:
        if valores['sg_campo'] not in dict(CambioSoftGuard.CAMPOS):
            errores.append('Campo de detección inválido.')
        else:
            consulta = consulta.filter(campo=valores['sg_campo'])
    if errores: consulta = consulta.none()
    cantidad = consulta.count()
    cantidad_odt = consulta.order_by().values('odt_id').distinct().count()
    pagina = Paginator(consulta,50).get_page(parametros.get('page_detalle'))
    filas = []
    for cambio in pagina.object_list:
        filas.append({'numero':cambio.odt.numero, 'campo':cambio.get_campo_display(),
            'es_monto':cambio.campo=='valor_pago_tecnico',
            'anterior':cambio.valor_anterior, 'nuevo':cambio.valor_nuevo,
            'diferencia':Decimal(cambio.valor_nuevo)-Decimal(cambio.valor_anterior)
                if cambio.campo=='valor_pago_tecnico' else None,
            'detectado_en':cambio.detectado_en, 'ejecucion_id':cambio.ejecucion_id})
    qs=parametros.copy();qs.pop('page_detalle',None)
    mantener=[(k,parametros[k]) for k in ('coordinador','tipo','correccion','q','page') if k in parametros]
    return {'filas':filas,'pagina':pagina,'cantidad':cantidad,'cantidad_odt':cantidad_odt,
            'filtros':valores,'errores':errores,'querystring':qs.urlencode(), 'mantener':mantener}
