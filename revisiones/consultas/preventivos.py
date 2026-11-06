"""La misma definición de preventivo para bandeja, análisis y cuentas."""
from django.db.models import Max
from django.db.models.functions import Coalesce, Lower, Trim

from ..dominio.cuentas import normalizar_codigo_cuenta
from ..dominio.servicios import SERVICIOS_PREVENTIVOS
from ..models import ODT
from .servicios import servicio_normalizado


def preventivos():
    return ODT.objects.annotate(
        servicio_efectivo=Coalesce("servicio_editado", "servicio"),
        servicio_normalizado=servicio_normalizado(),
        estado_normalizado=Lower(Trim("estado_softguard")),
    ).filter(servicio_normalizado__in=SERVICIOS_PREVENTIVOS)


def ultimos_preventivos(cuentas):
    """Una consulta agregada, agrupada luego por código estable de cuenta.

    Se lee el agregado global porque el nombre/dirección histórico puede ser
    diferente del texto actual. No se consulta una vez por cada cuenta u ODT.
    Solo se retienen las cuentas pedidas; un código inválido no atribuye visitas.
    """
    codigos = {c for texto in cuentas if (c := normalizar_codigo_cuenta(texto))}
    if not codigos:
        return {}
    grupos = (
        preventivos().filter(estado_normalizado="finalizado", fecha_finalizacion__isnull=False)
        .order_by().values("cuenta_completa").annotate(ultima=Max("fecha_finalizacion"))
    )
    ultimos = {}
    for grupo in grupos.iterator(chunk_size=1000):
        codigo = normalizar_codigo_cuenta(grupo["cuenta_completa"])
        if codigo not in codigos:
            continue
        fecha = grupo["ultima"]
        if codigo not in ultimos or fecha > ultimos[codigo]:
            ultimos[codigo] = fecha
    return ultimos


def asignar_ultimos_preventivos(filas):
    """Enriquecer una página ya obtenida sin cambiar su alcance ni el queryset."""
    filas = list(filas)
    ultimos = ultimos_preventivos(o.cuenta_completa for o in filas)
    for odt in filas:
        odt.fecha_ultimo_preventivo = ultimos.get(normalizar_codigo_cuenta(odt.cuenta_completa))
    return filas
