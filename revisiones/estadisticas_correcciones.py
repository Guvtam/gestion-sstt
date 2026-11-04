from collections import defaultdict
from decimal import Decimal
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render
from .models import CorreccionODT
from .coordinadores_softguard import identificar_coordinador_odt


@login_required
@permission_required('revisiones.ver_bandeja_sstt', raise_exception=True)
def estadisticas_correcciones(request):
    """Estadísticas por ODT, no por evento histórico; incluye estados actualizados."""
    qs = CorreccionODT.objects.select_related('odt').order_by('odt__numero')
    coordinador_filtro = request.GET.get('coordinador', '').strip()
    estado_filtro = request.GET.get('estado', '').strip()
    tipo_filtro = request.GET.get('tipo', '').strip()
    if estado_filtro in ('PENDIENTE', 'EN_PROCESO', 'ACTUALIZADA'):
        qs = qs.filter(estado=estado_filtro)
    if tipo_filtro == 'MONTO':
        qs = qs.filter(corrige_monto=True, corrige_servicio=False)
    elif tipo_filtro == 'SERVICIO':
        qs = qs.filter(corrige_monto=False, corrige_servicio=True)
    elif tipo_filtro == 'AMBOS':
        qs = qs.filter(corrige_monto=True, corrige_servicio=True)

    def nuevo():
        return {'cantidad': 0, 'solo_monto': 0, 'solo_servicio': 0,
                'ambos': 0, 'monto': 0, 'servicio': 0,
                'pendiente': 0, 'en_proceso': 0, 'actualizada': 0,
                'original': Decimal('0'), 'corregido': Decimal('0'), 'diferencia': Decimal('0')}

    total = nuevo()
    grupos = defaultdict(nuevo)
    nombres = {}
    for seguimiento in qs.iterator(chunk_size=200):
        odt = seguimiento.odt
        try:
            info = identificar_coordinador_odt(odt.numero) or {}
        except Exception:
            info = {}
        usuario = str(info.get('usuario') or 'SIN_IDENTIFICAR')
        nombre = info.get('nombre') or 'Sin identificar'
        nombres[usuario] = nombre
        if coordinador_filtro and coordinador_filtro != usuario:
            continue
        monto_original = odt.valor_pago_tecnico if odt.valor_pago_tecnico is not None else Decimal('0')
        monto_corregido = seguimiento.monto_objetivo if seguimiento.corrige_monto else monto_original
        # Si la ODT solo corrige servicio, no se cuenta como corrección de monto.
        for destino in (total, grupos[usuario]):
            destino['cantidad'] += 1
            if seguimiento.corrige_monto:
                destino['monto'] += 1
            if seguimiento.corrige_servicio:
                destino['servicio'] += 1
            if seguimiento.corrige_monto and seguimiento.corrige_servicio:
                destino['ambos'] += 1
            elif seguimiento.corrige_monto:
                destino['solo_monto'] += 1
            elif seguimiento.corrige_servicio:
                destino['solo_servicio'] += 1
            destino[seguimiento.estado.lower()] = destino.get(seguimiento.estado.lower(), 0) + 1
            destino['original'] += monto_original
            destino['corregido'] += monto_corregido
            destino['diferencia'] += monto_corregido - monto_original

    filas = [{'usuario': k, 'nombre': nombres.get(k, k), **v} for k, v in grupos.items()]
    filas.sort(key=lambda x: (-x['cantidad'], x['nombre']))
    opciones = sorted([{'usuario': k, 'nombre': v} for k, v in nombres.items()], key=lambda x: x['nombre'])
    return render(request, 'revisiones/estadisticas_correcciones.html', {
        'total': total, 'filas': filas, 'coordinadores': opciones,
        'coordinador_filtro': coordinador_filtro, 'estado_filtro': estado_filtro,
        'tipo_filtro': tipo_filtro,
    })
