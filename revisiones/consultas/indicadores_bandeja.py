"""Agregaciones de la bandeja sobre un queryset ya filtrado y autorizado."""
from decimal import Decimal
from django.db.models import Count, Q, Sum
from .pagos import condicion_aprobada, importe_efectivo
from .servicios import servicio_normalizado
from ..dominio.pagos import ESTADOS_APROBADOS
from ..dominio.servicios import nombres_canonicos

def indicadores_financieros(registros):
    from django.db.models import Q as FiltroQ

    # Evitamos transportar los cálculos de SLA,
    # incidencias y preventivos a la consulta financiera.
    base_indicadores = registros.annotate(servicio_resumen=servicio_normalizado()).order_by().values(
        "pk",
        "valor_pago_tecnico",
        "valor_pago_editado",
        "revision__estado",
    )

    # El mismo catálogo clasifica tarjetas e instantáneas de facturación.
    condicion_mantencion_con_cobro = Q(servicio_resumen__in=nombres_canonicos("correctiva_con_cobro"))
    condicion_mantencion_sin_cobro = Q(servicio_resumen__in=nombres_canonicos("correctiva_sin_cobro"))
    condicion_renovacion = Q(servicio_resumen__in=nombres_canonicos("renovacion"))
    condicion_mantenimiento_preventivo = Q(servicio_resumen__in=nombres_canonicos("preventivo"))
    condicion_acuerdo_comercial = Q(servicio_resumen__in=nombres_canonicos("acuerdo_comercial"))
    condicion_presupuesto = Q(servicio_resumen__in=nombres_canonicos("presupuesto"))
    condicion_cruzverde = Q(servicio_resumen__in=nombres_canonicos("nueva_instalacion_cruzverde"))

    indicadores_sql = base_indicadores.aggregate(
        cantidad_total=Count("pk"),
        monto_original=Sum("valor_pago_tecnico"),

        cantidad_aprobadas=Count(
            "pk",
            filter=(
                FiltroQ(revision__isnull=True)
                | FiltroQ(
                    revision__estado__in=ESTADOS_APROBADOS
                )
            ),
        ),
        monto_aprobadas=Sum(
            importe_efectivo(),
            filter=condicion_aprobada(),
        ),

        cantidad_en_revision=Count(
            "pk",
            filter=FiltroQ(revision__estado="EN_REVISION"),
        ),
        monto_en_revision=Sum(
            importe_efectivo(),
            filter=FiltroQ(revision__estado="EN_REVISION"),
        ),

        cantidad_rechazadas=Count(
            "pk",
            filter=FiltroQ(revision__estado="RECHAZADA"),
        ),
        monto_rechazadas=Sum(
            importe_efectivo(),
            filter=FiltroQ(revision__estado="RECHAZADA"),
        ),

        cantidad_por_revisar=Count(
            "pk",
            filter=(
                FiltroQ(revision__isnull=True)
                | FiltroQ(revision__estado="POR_REVISAR")
            ),
        ),
        monto_por_revisar=Sum(
            importe_efectivo(),
            filter=(
                FiltroQ(revision__isnull=True)
                | FiltroQ(revision__estado="POR_REVISAR")
            ),
        ),

        cantidad_observadas=Count(
            "pk",
            filter=FiltroQ(revision__estado="OBSERVADA"),
        ),
        monto_observadas=Sum(
            importe_efectivo(),
            filter=FiltroQ(revision__estado="OBSERVADA"),
        ),

        cantidad_mantencion_con_cobro=Count(
            "pk",
            filter=condicion_mantencion_con_cobro,
        ),
        monto_mantencion_con_cobro=Sum(
            importe_efectivo(),
            filter=condicion_mantencion_con_cobro,
        ),

        cantidad_mantencion_sin_cobro=Count(
            "pk",
            filter=condicion_mantencion_sin_cobro,
        ),
        monto_mantencion_sin_cobro=Sum(
            importe_efectivo(),
            filter=condicion_mantencion_sin_cobro,
        ),

        cantidad_renovacion=Count(
            "pk", filter=condicion_renovacion,
        ),
        monto_renovacion=Sum(
            importe_efectivo(), filter=condicion_renovacion,
        ),
        cantidad_mantenimiento_preventivo=Count(
            "pk", filter=condicion_mantenimiento_preventivo,
        ),
        monto_mantenimiento_preventivo=Sum(
            importe_efectivo(), filter=condicion_mantenimiento_preventivo,
        ),
        cantidad_acuerdo_comercial=Count("pk", filter=condicion_acuerdo_comercial),
        monto_acuerdo_comercial=Sum(importe_efectivo(), filter=condicion_acuerdo_comercial),
        cantidad_presupuesto=Count("pk", filter=condicion_presupuesto),
        monto_presupuesto=Sum(importe_efectivo(), filter=condicion_presupuesto),
        cantidad_nueva_instalacion_cruzverde=Count("pk", filter=condicion_cruzverde),
        monto_nueva_instalacion_cruzverde=Sum(importe_efectivo(), filter=condicion_cruzverde),
    )

    def construir_indicador(nombre):
        return {
            "cantidad": indicadores_sql[f"cantidad_{nombre}"],
            "monto": (
                indicadores_sql[f"monto_{nombre}"]
                or Decimal("0")
            ),
        }

    total = {
        "cantidad": indicadores_sql["cantidad_total"],
        "monto": (
            indicadores_sql["monto_original"]
            or Decimal("0")
        ),
    }

    aprobadas = construir_indicador("aprobadas")
    en_revision = construir_indicador("en_revision")
    rechazadas = construir_indicador("rechazadas")
    por_revisar = construir_indicador("por_revisar")
    observadas = construir_indicador("observadas")
    mantencion_con_cobro = construir_indicador("mantencion_con_cobro")
    mantencion_sin_cobro = construir_indicador("mantencion_sin_cobro")
    renovacion = construir_indicador("renovacion")
    mantenimiento_preventivo = construir_indicador("mantenimiento_preventivo")

    return {
        "total": total,
        "aprobadas": aprobadas,
        "en_revision": en_revision,
        "rechazadas": rechazadas,
        "por_revisar": por_revisar,
        "observadas": observadas,
        "mantencion_con_cobro": mantencion_con_cobro,
        "mantencion_sin_cobro": mantencion_sin_cobro,
        "renovacion": renovacion,
        "mantenimiento_preventivo": mantenimiento_preventivo,
        "acuerdo_comercial": construir_indicador("acuerdo_comercial"),
        "presupuesto": construir_indicador("presupuesto"),
        "nueva_instalacion_cruzverde": construir_indicador("nueva_instalacion_cruzverde"),
    }


def indicadores_operativos(registros):
    kpis_correcciones = registros.aggregate(
        odt_modificadas=Count(
            "pk",
            filter=(
                Q(servicio_editado__isnull=False)
                | Q(valor_pago_editado__isnull=False)
            ),
            distinct=True,
        ),
        servicios_pendientes=Count(
            "pk",
            filter=(
                Q(seguimiento_correccion__corrige_servicio=True)
                & Q(seguimiento_correccion__estado__in=[
                    "PENDIENTE",
                    "EN_PROCESO",
                ])
            ),
            distinct=True,
        ),
        montos_pendientes=Count(
            "pk",
            filter=(
                Q(seguimiento_correccion__corrige_monto=True)
                & Q(seguimiento_correccion__estado__in=[
                    "PENDIENTE",
                    "EN_PROCESO",
                ])
            ),
            distinct=True,
        ),
    )

    kpi_odt_modificadas = (
        kpis_correcciones["odt_modificadas"] or 0
    )

    kpi_servicios_corregir = (
        kpis_correcciones["servicios_pendientes"] or 0
    )

    kpi_montos_corregir = (
        kpis_correcciones["montos_pendientes"] or 0
    )

    return {
        "kpi_odt_modificadas": kpi_odt_modificadas,
        "kpi_servicios_corregir": kpi_servicios_corregir,
        "kpi_montos_corregir": kpi_montos_corregir,
    }


def indicador(qs):
    valores = qs.aggregate(
        cantidad=Count("id"),
        monto=Sum(importe_efectivo()),
    )
    return {
        "cantidad": valores["cantidad"],
        "monto": valores["monto"] or Decimal("0"),
    }

