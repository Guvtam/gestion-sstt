"""Indicadores por lotes: tres consultas, sin subconsultas por cada ODT."""
from datetime import timedelta
from collections import Counter
from django.db.models import Count, Max, Subquery
from django.utils import timezone
from .models import ODT
from .cuentas_utils import normalizar_codigo_cuenta


def cargar_metricas(queryset):
    cuentas = queryset.order_by().values("cuenta_completa")
    ahora = timezone.now()
    finalizadas = ODT.objects.filter(
        cuenta_completa__in=Subquery(cuentas), estado_softguard__iexact="Finalizado",
    )
    grupos_incidencias = list(
        ODT.objects.filter(estado_softguard__iexact="Finalizado",
                           fecha_finalizacion__range=(ahora-timedelta(days=90),ahora))
        .exclude(cuenta_completa="").exclude(cuenta_completa__isnull=True)
        .order_by().values("cuenta_completa","contratista").annotate(total=Count("pk"))
    )
    incidencias = {}
    incidencias_cuenta = Counter()
    for r in grupos_incidencias:
        if r["contratista"]:
            incidencias[(r["cuenta_completa"],r["contratista"])] = r["total"]
        codigo = normalizar_codigo_cuenta(r["cuenta_completa"]) or r["cuenta_completa"].strip().upper()
        if codigo:
            incidencias_cuenta[codigo] += r["total"]
    preventivos = dict(finalizadas.filter(
        servicio__iexact="MANTENIMIENTO PREVENTIVO",fecha_finalizacion__isnull=False,
    ).order_by().values("cuenta_completa").annotate(ultima=Max("fecha_finalizacion"))
     .values_list("cuenta_completa","ultima"))
    filas = list(queryset.only("numero","cuenta_completa","contratista","tecnico","servicio",
                              "servicio_editado","fecha_creacion","fecha_finalizacion","estado_softguard"))
    for o in filas:
        o.servicio_efectivo=o.servicio_editado if o.servicio_editado is not None else o.servicio
        o.cantidad_incidencias=incidencias.get((o.cuenta_completa,o.contratista),0)
        o.clave_cuenta_analisis=normalizar_codigo_cuenta(o.cuenta_completa) or (o.cuenta_completa or "").strip().upper()
        o.incidencias_cuenta_90=incidencias_cuenta.get(o.clave_cuenta_analisis,0)
        o.fecha_ultimo_preventivo=preventivos.get(o.cuenta_completa)
        o.duracion_sla=(o.fecha_finalizacion-o.fecha_creacion) if o.fecha_finalizacion and o.fecha_creacion else None
        o.estado_sla=("SIN_DATOS" if o.fecha_creacion is None else "PENDIENTE" if o.fecha_finalizacion is None
                      else "ERROR_FECHAS" if o.duracion_sla<timedelta(0)
                      else "CUMPLE" if o.duracion_sla<=timedelta(hours=48) else "NO_CUMPLE")
    return filas
