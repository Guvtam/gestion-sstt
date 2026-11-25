"""Orden permitido; los datos de coordinador nunca se usan aquí para autorizar."""
import unicodedata
from django.db.models import F
from django.db.models.functions import Lower, Trim

OPCIONES_ORDEN = (
    ('', 'Orden habitual'), ('cuenta', 'Cuenta'), ('numero', 'Número de ODT'),
    ('contratista', 'Contratista'), ('coordinador', 'Coordinador'),
    ('finalizacion', 'Fecha de finalización'),
)


def leer_orden(parametros):
    orden = parametros.get('orden', '')
    if orden not in dict(OPCIONES_ORDEN):
        orden = ''
    direccion = 'desc' if parametros.get('direccion') == 'desc' else 'asc'
    return orden, direccion


def expresiones_orden(orden, direccion):
    campo = {'cuenta': Lower(Trim('cuenta_completa')), 'numero': F('numero'),
             'contratista': Lower(Trim('contratista')), 'finalizacion': F('fecha_finalizacion')}[orden]
    principal = campo.desc(nulls_last=True) if direccion == 'desc' else campo.asc(nulls_last=True)
    return (principal, 'numero', 'pk')


def clave_nombre(texto):
    return ''.join(c for c in unicodedata.normalize('NFKD', texto.strip().casefold()) if not unicodedata.combining(c))


def ids_por_coordinador(registros, direccion, *, priorizar_fallos, resolver):
    """Solo PK/número/bandera; resolver por lotes y cargar después la página visible."""
    campos = ['pk', 'numero'] + (['es_fallo_prueba'] if priorizar_fallos else [])
    filas = list(registros.order_by().values_list(*campos))
    datos = resolver([f[1] for f in filas])
    # Desempate estable en ambas direcciones. No disponible permanece al final.
    filas.sort(key=lambda f: (f[1], f[0]))
    filas.sort(key=lambda f: clave_nombre(datos[f[1]].get('nombre') or 'Sin identificar'), reverse=direccion == 'desc')
    filas.sort(key=lambda f: datos[f[1]].get('disponible', True) is False)
    if priorizar_fallos:
        filas.sort(key=lambda f: bool(f[2]))
    return [f[0] for f in filas]
