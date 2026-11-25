"""Indicadores por lotes: hasta tres consultas, sin consulta por cada ODT."""
from collections import Counter
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

from .consultas.preventivos import asignar_ultimos_preventivos
from .consultas.pagos import importe_efectivo
from .dominio.cuentas import normalizar_codigo_cuenta
from .dominio.indicadores import estado_sla
from .dominio.servicios import servicio_efectivo
from .models import ODT


def cargar_metricas(queryset, *, hasta=None):
    from .consultas.ventanas_incidencias import referencia_incidencias
    ahora, operador_fin = referencia_incidencias(hasta)
    grupos_incidencias = (
        ODT.objects.filter(
            estado_softguard__iexact="Finalizado",
            fecha_finalizacion__gte=ahora-timedelta(days=90),
            **{f"fecha_finalizacion__{operador_fin}": ahora},
        )
        .exclude(cuenta_completa="")
        .exclude(cuenta_completa__isnull=True)
        .order_by()
        .values("cuenta_completa", "contratista")
        .annotate(total=Count("pk"),
            total_60=Count("pk",filter=Q(fecha_finalizacion__gte=ahora-timedelta(days=60))),
            total_30=Count("pk",filter=Q(fecha_finalizacion__gte=ahora-timedelta(days=30))))
    )
    incidencias = {}
    incidencias_60, incidencias_30 = {}, {}
    incidencias_cuenta = Counter()
    for grupo in grupos_incidencias.iterator(chunk_size=1000):
        cuenta = grupo["cuenta_completa"]
        if grupo["contratista"]:
            incidencias[(cuenta, grupo["contratista"])] = grupo["total"]
            incidencias_60[(cuenta,grupo["contratista"])]=grupo["total_60"]
            incidencias_30[(cuenta,grupo["contratista"])]=grupo["total_30"]
        codigo = normalizar_codigo_cuenta(cuenta) or cuenta.strip().upper()
        if codigo:
            incidencias_cuenta[codigo] += grupo["total"]

    filas = list(queryset.annotate(monto_efectivo=importe_efectivo()).only(
        "numero", "cuenta_completa", "contratista", "tecnico", "servicio",
        "servicio_editado", "fecha_creacion", "fecha_finalizacion", "estado_softguard",
    ))
    asignar_ultimos_preventivos(filas)
    for odt in filas:
        odt.servicio_efectivo = servicio_efectivo(odt.servicio, odt.servicio_editado)
        odt.cantidad_incidencias = incidencias.get((odt.cuenta_completa, odt.contratista), 0)
        odt.cantidad_incidencias_60=incidencias_60.get((odt.cuenta_completa,odt.contratista),0)
        odt.cantidad_incidencias_30=incidencias_30.get((odt.cuenta_completa,odt.contratista),0)
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
