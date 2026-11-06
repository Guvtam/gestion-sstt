"""Reglas de SLA, incidencias a 90 días y último preventivo compartidas."""
from datetime import timedelta
from django.utils import timezone
from django.db.models import (Q, Count, OuterRef, Subquery, IntegerField, Case, When,
    Value, ExpressionWrapper, DurationField, F, CharField)
from django.db.models.functions import Coalesce
from .models import ODT


def con_indicadores_odt(queryset):
    fecha_inicio_incidencias = timezone.now() - timedelta(days=90)

    incidencias_ventana = (
        ODT.objects
        .filter(
            cuenta_completa=OuterRef("cuenta_completa"),
            contratista=OuterRef("contratista"),
            estado_softguard__iexact="Finalizado",
            fecha_finalizacion__gte=fecha_inicio_incidencias,
            fecha_finalizacion__lte=timezone.now(),
        )
        .exclude(contratista__isnull=True)
        .exclude(contratista="")
        .exclude(cuenta_completa__isnull=True)
        .exclude(cuenta_completa="")
    )

    incidencias_periodo = (
        incidencias_ventana
        .order_by()
        .values("cuenta_completa", "contratista")
        .annotate(total=Count("pk"))
        .values("total")[:1]
    )


    # ==================================================
    # ÚLTIMO MANTENIMIENTO PREVENTIVO
    # ==================================================

    ultimo_preventivo = (
        ODT.objects
        .filter(
            cuenta_completa=OuterRef("cuenta_completa"),
            servicio__iexact="MANTENIMIENTO PREVENTIVO",
            estado_softguard__iexact="Finalizado",
            fecha_finalizacion__isnull=False,
        )
        .order_by("-fecha_finalizacion")
        .values("fecha_finalizacion")[:1]
    )

    # ==================================================
    # CONSULTA PRINCIPAL DE ODT
    # ==================================================

    registros = (
        queryset

        # Duración del SLA.
        .annotate(
            duracion_sla=ExpressionWrapper(
                F("fecha_finalizacion") - F("fecha_creacion"),
                output_field=DurationField(),
            )
        )

        # Último preventivo de la cuenta.
        .annotate(
            fecha_ultimo_preventivo=Subquery(
                ultimo_preventivo
            )
        )

        
        # Contador de incidencias:
        # mismo contratista y misma cuenta en 90 días.
        .annotate(
            cantidad_incidencias=Case(
                When(
                    Q(contratista__isnull=False)
                    & ~Q(contratista="")
                    & Q(cuenta_completa__isnull=False)
                    & ~Q(cuenta_completa=""),

                    then=Coalesce(
                        Subquery(
                            incidencias_periodo,
                            output_field=IntegerField(),
                        ),
                        Value(0),
                        output_field=IntegerField(),
                    ),
                ),
                default=Value(0),
                output_field=IntegerField(),
            )
        )


        # Estado del SLA.
        .annotate(
            estado_sla=Case(
                When(
                    fecha_creacion__isnull=True,
                    then=Value("SIN_DATOS"),
                ),
                When(
                    fecha_finalizacion__isnull=True,
                    then=Value("PENDIENTE"),
                ),
                When(
                    duracion_sla__lt=timedelta(0),
                    then=Value("ERROR_FECHAS"),
                ),
                When(
                    duracion_sla__lte=timedelta(hours=48),
                    then=Value("CUMPLE"),
                ),
                default=Value("NO_CUMPLE"),
                output_field=CharField(),
            )
        )

        .order_by(
            "cuenta_completa",
            "codigo_tecnico",
            "fecha_finalizacion",
            "-numero",
        )
    )

    return registros
