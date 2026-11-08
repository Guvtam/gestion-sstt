"""Filtros ORM sin request, render ni permisos; no usar para autorizar alcance."""
from datetime import date
from django.db.models import Q
from .pagos import condicion_aprobada
from ..dominio.filtros_bandeja import SIN_TECNICO_FILTRO

def filtrar_disponibles(registros, *, filtros, servicios_seleccionados, campo_fecha):
    if filtros["estado"]:
        registros = registros.filter(estado_softguard=filtros["estado"])

    # Filtrar por servicios seleccionados.
    if servicios_seleccionados:
        registros = registros.filter(
            Q(
                servicio_editado__isnull=True,
                servicio__in=servicios_seleccionados,
            )
            | Q(
                servicio_editado__in=servicios_seleccionados
            )
        )

    # Filtrar por fechas de finalización.
    for campo, operador in (
        ("fecha_desde", "gte"),
        ("fecha_hasta", "lte"),
    ):
        valor = filtros[campo]

        if valor:
            try:
                fecha_valida = date.fromisoformat(valor)
            except ValueError:
                continue

            registros = registros.filter(
                **{
                    f"{campo_fecha}__date__{operador}":
                        fecha_valida
                }
            )

    return registros


def filtrar_tabla(registros, *, filtros, servicios_seleccionados, contratistas_seleccionados, campo_fecha, por_creacion, numero_exacto, avisar_fecha):
    # Contratista.
    if contratistas_seleccionados:
        condicion_contratistas = Q(contratista__in=[
            nombre for nombre in contratistas_seleccionados if nombre != SIN_TECNICO_FILTRO
        ])
        if por_creacion and SIN_TECNICO_FILTRO in contratistas_seleccionados:
            condicion_contratistas |= Q(contratista="") | Q(contratista__isnull=True)
        registros = registros.filter(condicion_contratistas)
    else:
        registros = registros.none()

    # Estado SoftGuard.
    if filtros["estado"]:
        registros = registros.filter(
            estado_softguard=filtros["estado"]
        )



    # Estado de revisión.
    if filtros["revision"] in ("APROBADA", "POR_REVISAR"):
        registros = registros.filter(
            condicion_aprobada()
        )

    elif filtros["revision"]:
        registros = registros.filter(
            revision__estado=filtros["revision"]
        )

    # Servicios originales y corregidos.
    if servicios_seleccionados:
        registros = registros.filter(
            Q(
                servicio_editado__isnull=True,
                servicio__in=servicios_seleccionados,
            )
            | Q(
                servicio_editado__in=servicios_seleccionados
            )
        )

    # Fechas de finalización.
    for campo, operador in (
        ("fecha_desde", "gte"),
        ("fecha_hasta", "lte"),
    ):

        valor = filtros[campo]

        if valor:
            try:
                date.fromisoformat(valor)

            except ValueError:
                avisar_fecha(valor)

            else:
                registros = registros.filter(
                    **{
                        f"{campo_fecha}__date__{operador}":
                            valor
                    }
                )


    # ==================================================
    # BÚSQUEDA GENERAL DE ODT
    # Incluye observaciones de SoftGuard
    # ==================================================

    if filtros["q"]:

        q = filtros["q"]

        condicion = (
            Q(contratista__icontains=q)
            | Q(tecnico__icontains=q)
            | Q(cuenta_completa__icontains=q)
            | Q(servicio__icontains=q)
            | Q(servicio_editado__icontains=q)
            | Q(direccion__icontains=q)
            | Q(observaciones_insumos__icontains=q)
        )

        # Permitir búsqueda por número de ODT.
        if q.isdigit():
            condicion |= Q(numero=int(q))

        registros = registros.filter(condicion)


    # ==================================================
    # FILTRO POR COORDINADOR SOFTGUARD
    # ==================================================

    # Enlace desde el historial: coincidencia exacta sin ampliar el alcance del usuario.
    if numero_exacto is not None:
        if numero_exacto.isascii() and numero_exacto.isdigit() and len(numero_exacto) <= 10:
            registros = registros.filter(numero=int(numero_exacto))
        else:
            registros = registros.none()

    return registros


def opciones_contratistas(queryset, incluir_sin_tecnico=False):
    valores = list(queryset.order_by("contratista").values_list("contratista", flat=True).distinct())
    nombres = [v for v in valores if v]
    if incluir_sin_tecnico:
        nombres.append(SIN_TECNICO_FILTRO)
    return nombres

