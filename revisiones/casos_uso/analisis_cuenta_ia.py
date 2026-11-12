"""Piloto de solo lectura: selección exacta, cobertura y envío explícito."""
from collections import Counter
from datetime import date, datetime, time, timedelta
import json
import re

from django.utils import timezone

from ..dominio.analisis_cuenta_ia import AnalisisNoDisponible, depurar_texto
from ..dominio.cuentas import normalizar_codigo_cuenta
from ..dominio.servicios import servicio_efectivo
from ..integraciones.ia_cuentas import leer_historiales
from ..models import ODT


def seleccionar(codigo, desde, hasta):
    codigo = str(codigo or '').strip().upper()
    if not re.fullmatch(r'[A-Z0-9]{1,20}-[A-Z0-9]{1,20}',codigo):
        raise AnalisisNoDisponible('Selecciona un código de cuenta válido, por ejemplo FIR-3302.')
    try:
        inicio, fin = date.fromisoformat(desde), date.fromisoformat(hasta)
        if inicio > fin or (fin-inicio).days > 366:
            raise ValueError()
        limite = fin + timedelta(days=1)
    except (ValueError, TypeError, OverflowError):
        raise AnalisisNoDisponible('Selecciona fechas válidas y un período máximo de un año.') from None
    linea, numero = codigo.split('-')
    patron = r'^\s*'+re.escape(linea)+r'\s*-\s*'+re.escape(numero)+r'(?=\s+-\s+|$)'
    filas = list(ODT.objects.filter(estado_softguard__iexact='Finalizado',
        fecha_finalizacion__gte=timezone.make_aware(datetime.combine(inicio,time.min)),
        fecha_finalizacion__lt=timezone.make_aware(datetime.combine(limite,time.min)),
        cuenta_completa__iregex=patron).only('numero','cuenta_completa','servicio','servicio_editado',
            'fecha_finalizacion','observaciones_insumos').order_by('fecha_finalizacion','numero')[:101])
    filas = [o for o in filas if normalizar_codigo_cuenta(o.cuenta_completa) == codigo]
    if not filas:
        raise AnalisisNoDisponible('No hay ODT finalizadas para esa cuenta y período en la base local.')
    if len(filas) > 100:
        raise AnalisisNoDisponible('La cuenta supera 100 ODT en el período. Reduce las fechas para esta prueba.')
    return codigo, filas


def preparar(codigo, desde, hasta):
    codigo, filas = seleccionar(codigo, desde, hasta)
    numeros = {o.numero for o in filas}
    eventos = {n:[] for n in numeros}
    for e in leer_historiales(sorted(numeros)):
        if e['NumeroODT'] not in numeros:
            raise AnalisisNoDisponible('El origen devolvió eventos fuera de la selección.')
        eventos[e['NumeroODT']].append(e)
    odts = []
    fuentes = []
    for odt in filas:
        registros = [{'id':f'{odt.numero}-OBS', 'fecha':timezone.localtime(odt.fecha_finalizacion).isoformat(),
                      'accion':'Observación de la ODT', 'texto':depurar_texto(odt.observaciones_insumos)}]
        for i,e in enumerate(eventos[odt.numero],1):
            registros.append({'id':f'{odt.numero}-E{i}', 'fecha':str(e['FechaHora'] or ''),
                             'accion':depurar_texto(e['Accion']), 'texto':depurar_texto(e['Observacion'])})
        odts.append({'numero':odt.numero, 'servicio':depurar_texto(servicio_efectivo(odt.servicio, odt.servicio_editado)),
                     'finalizacion':timezone.localtime(odt.fecha_finalizacion).isoformat(), 'fuentes':registros})
        fuentes.extend(registros)
    # La identidad de cuenta y los nombres no son necesarios para el proveedor.
    datos = {'desde':desde, 'hasta':hasta, 'criterio':'ODT finalizadas; todos los servicios', 'odts':odts}
    if len(json.dumps(datos, ensure_ascii=False).encode()) > 180000:
        raise AnalisisNoDisponible('Los antecedentes exceden el tamaño de esta prueba. Reduce el período.')
    return {'codigo':codigo,'datos':datos,'cantidad':len(filas),
            'con_historial':sum(bool(v) for v in eventos.values()),
            'eventos':sum(len(v) for v in eventos.values()),
            'textos_recortados':sum('[texto recortado]' in f['texto'] for f in fuentes),
            'servicios':sorted(Counter(o['servicio'] for o in odts).items())}
