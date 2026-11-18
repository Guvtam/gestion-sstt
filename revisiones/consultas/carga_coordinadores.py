"""Carga total por fecha de creación; independiente de los filtros de correcciones."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from django.db.models import BooleanField, Case, Q, Value, When
from django.utils import timezone
from ..coordinadores_softguard import CoordinadoresNoDisponibles


def resumir_carga(registros, parametros, resolver, *, hoy):
    desde = parametros.get('carga_desde', hoy.replace(month=1, day=1).isoformat()).strip()
    hasta = parametros.get('carga_hasta', hoy.isoformat()).strip()
    fechas = {}
    errores = []
    for nombre, texto in (('desde', desde), ('hasta', hasta)):
        if texto:
            try:
                fechas[nombre] = date.fromisoformat(texto)
            except ValueError:
                errores.append('Indica fechas válidas para el total de ODT.')
    if fechas.get('desde') and fechas.get('hasta') and fechas['desde'] > fechas['hasta']:
        errores.append('La fecha inicial del total de ODT no puede superar la fecha final.')
    if not errores:
        try:
            if 'desde' in fechas:
                registros = registros.filter(fecha_creacion__gte=timezone.make_aware(
                    datetime.combine(fechas['desde'], time.min)))
            if 'hasta' in fechas:
                registros = registros.filter(fecha_creacion__lt=timezone.make_aware(
                    datetime.combine(fechas['hasta'] + timedelta(days=1), time.min)))
        except (ValueError, OverflowError):
            errores.append('El período del total de ODT está fuera de rango.')
    if errores:
        registros = registros.none()
    registros = registros.order_by('numero').annotate(tiene_correccion=Case(
        When(Q(seguimiento_correccion__isnull=False) | Q(servicio_editado__isnull=False)
             | Q(valor_pago_editado__isnull=False), then=Value(True)),
        default=Value(False), output_field=BooleanField(),
    )).values('numero', 'estado_softguard', 'tiene_correccion')
    grupos = {}
    nombres = {}
    estados = set()
    coordinador = parametros.get('coordinador', '').strip()
    lote = []

    def procesar(filas):
        # El mismo resolver de bandeja: asignación manual, proyección y origen.
        # Una falla se propaga; nunca se interpreta como Sin identificar.
        responsables = resolver([fila['numero'] for fila in filas])
        for fila in filas:
            info = responsables.get(fila['numero'])
            if (not isinstance(info, dict) or not isinstance(info.get('identificado'), bool)
                    or info.get('disponible', True) is False):
                raise CoordinadoresNoDisponibles()
            identificado = info.get('identificado') is True and bool(info.get('usuario'))
            usuario = str(info['usuario']) if identificado else 'SIN_IDENTIFICAR'
            nombre = (info.get('nombre') or usuario) if identificado else 'Sin coordinador identificado'
            nombres[usuario] = nombre
            if coordinador and coordinador != usuario:
                continue
            estado = str(fila['estado_softguard'] or '').strip() or 'Sin estado'
            estados.add(estado)
            grupo = grupos.setdefault(usuario, {'usuario':usuario, 'nombre':nombre, 'cantidad':0,
                'con_correcciones':0, 'estados':defaultdict(int)})
            grupo['cantidad'] += 1
            grupo['con_correcciones'] += int(fila['tiene_correccion'])
            grupo['estados'][estado] += 1

    disponible = not errores
    try:
        for fila in registros.iterator(chunk_size=250):
            lote.append(fila)
            if len(lote) == 250:
                procesar(lote)
                lote = []
        if lote:
            procesar(lote)
    except CoordinadoresNoDisponibles:
        disponible = False
        grupos.clear()
        estados.clear()
        nombres.clear()
        errores.append('Total no disponible: no se pudo verificar el coordinador de todas las ODT. Intenta nuevamente.')
    prioridad = {'Pendiente':0, 'Asignado':1, 'Finalizado':2}
    estados = sorted(estados, key=lambda e:(prioridad.get(e,3),e.casefold()))
    filas = sorted(grupos.values(), key=lambda g:(-g['cantidad'],g['nombre'].casefold(),g['usuario']))
    totales_estados = [sum(f['estados'][e] for f in filas) for e in estados]
    for fila in filas:
        fila['cantidades_estados'] = [fila['estados'][e] for e in estados]
        fila['estados'] = dict(fila['estados'])
    return {'disponible':disponible, 'filas':filas, 'estados':estados, 'totales_estados':totales_estados,
            'cantidad':sum(f['cantidad'] for f in filas),
            'con_correcciones':sum(f['con_correcciones'] for f in filas),
            'opciones':nombres, 'desde':desde, 'hasta':hasta, 'errores':list(dict.fromkeys(errores))}
