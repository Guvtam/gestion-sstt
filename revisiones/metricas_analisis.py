"""Indicadores por lotes: hasta tres consultas, sin consulta por cada ODT."""
from collections import Counter
from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from .consultas.preventivos import asignar_ultimos_preventivos
from .dominio.cuentas import normalizar_codigo_cuenta
from .dominio.indicadores import estado_sla
from .dominio.servicios import servicio_efectivo
from .models import ODT


def cargar_metricas(queryset):
    ahora = timezone.now()
    grupos_incidencias = (
        ODT.objects.filter(
            estado_softguard__iexact="Finalizado",
            fecha_finalizacion__range=(ahora - timedelta(days=90), ahora),
        )
        .exclude(cuenta_completa="")
        .exclude(cuenta_completa__isnull=True)
        .order_by()
        .values("cuenta_completa", "contratista")
        .annotate(total=Count("pk"))
    )
    incidencias = {}
    incidencias_cuenta = Counter()
    for grupo in grupos_incidencias.iterator(chunk_size=1000):
        cuenta = grupo["cuenta_completa"]
        if grupo["contratista"]:
            incidencias[(cuenta, grupo["contratista"])] = grupo["total"]
        codigo = normalizar_codigo_cuenta(cuenta) or cuenta.strip().upper()
        if codigo:
            incidencias_cuenta[codigo] += grupo["total"]

    filas = list(queryset.only(
        "numero", "cuenta_completa", "contratista", "tecnico", "servicio",
        "servicio_editado", "fecha_creacion", "fecha_finalizacion", "estado_softguard",
    ))
    asignar_ultimos_preventivos(filas)
    for odt in filas:
        odt.servicio_efectivo = servicio_efectivo(odt.servicio, odt.servicio_editado)
        odt.cantidad_incidencias = incidencias.get((odt.cuenta_completa, odt.contratista), 0)
        odt.clave_cuenta_analisis = (
            normalizar_codigo_cuenta(odt.cuenta_completa)
            or (odt.cuenta_completa or "").strip().upper()
        )
        odt.incidencias_cuenta_90 = incidencias_cuenta.get(odt.clave_cuenta_analisis, 0)
        odt.duracion_sla = (
            odt.fecha_finalizacion - odt.fecha_creacion
            if odt.fecha_finalizacion and odt.fecha_creacion else None
        )
        odt.estado_sla = estado_sla(odt.fecha_creacion, odt.fecha_finalizacion)
    return filas
