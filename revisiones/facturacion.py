from .cuentas_utils import cargar_catalogo_cuentas, tipo_cliente_cuenta

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import (
    login_required,
    permission_required,
)
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.urls import reverse
from django.views.decorators.http import (
    require_http_methods,
    require_POST,
)

from .models import ODT
from .facturacion_models import (
    PeriodoFacturacion,
    FacturacionContratista,
    FacturacionODT,
)


def _parametros(request):
    datos = request.GET if request.method == "GET" else request.POST

    try:
        desde = date.fromisoformat(
            datos.get("fecha_desde", "")
        )
        hasta = date.fromisoformat(
            datos.get("fecha_hasta", "")
        )
    except (ValueError, TypeError):
        raise ValueError(
            "Debes indicar ambas fechas válidas."
        )

    siguiente = (
        desde.replace(day=28) + timedelta(days=4)
    ).replace(day=1)

    if desde.day != 21 or hasta != siguiente.replace(day=20):
        raise ValueError(
            "El período debe comenzar el día 21 y "
            "terminar el día 20 del mes siguiente."
        )

    contratistas = [
        v for v in datos.getlist("contratista") if v
    ]

    servicios = [
        v for v in datos.getlist("servicios") if v
    ]

    return desde, hasta, contratistas, servicios, datos


def _odts(desde, hasta, contratistas, servicios, datos):

    qs = ODT.objects.filter(
        fecha_finalizacion__date__gte=desde,
        fecha_finalizacion__date__lte=hasta,
        estado_softguard__iexact="Finalizado",
    ).filter(
        Q(revision__isnull=True)
        | Q(revision__estado__in=(
            "APROBADA",
            "POR_REVISAR",
        ))
    )

    if datos.get("contratistas_filtrados") == "1" and not contratistas:
        return qs.none()

    if contratistas:
        qs = qs.filter(
            contratista__in=contratistas
        )
    else:
        qs = qs.exclude(
            contratista=""
        )

    if servicios:
        qs = qs.filter(
            Q(
                servicio_editado__isnull=True,
                servicio__in=servicios,
            )
            | Q(
                servicio_editado__in=servicios
            )
        )

    if datos.get("tipo_cliente"):
        qs = qs.filter(
            tipo_cliente=datos["tipo_cliente"]
        )

    if (
        datos.get("estado")
        and datos["estado"].lower() != "finalizado"
    ):
        return qs.none()

    # La facturación utiliza siempre la regla
    # de aprobación, independientemente del
    # filtro de revisión de la bandeja.

    q = datos.get("q", "").strip()

    if q:
        condicion = (
            Q(contratista__icontains=q)
            | Q(tecnico__icontains=q)
            | Q(cuenta_completa__icontains=q)
            | Q(servicio__icontains=q)
            | Q(servicio_editado__icontains=q)
            | Q(direccion__icontains=q)
        )

        if q.isdigit():
            condicion |= Q(numero=int(q))

        qs = qs.filter(condicion)

    return qs.order_by(
        "contratista",
        "numero",
    )


def _resumen(qs):

    grupos = defaultdict(
        lambda: {
            "odts": [],
            "monto": Decimal("0"),
        }
    )

    for odt in qs.iterator(chunk_size=1000):

        grupo = grupos[odt.contratista]

        grupo["odts"].append(odt)

        monto = (
            odt.valor_pago_editado
            if odt.valor_pago_editado is not None
            else odt.valor_pago_tecnico
        )

        grupo["monto"] += (
            monto if monto is not None
            else Decimal("0")
        )

    return [
        {
            "contratista": nombre,
            "cantidad": len(datos["odts"]),
            "monto": datos["monto"],
        }
        for nombre, datos in sorted(grupos.items())
    ]


@login_required
@permission_required(
    "revisiones.exportar_pagos_sstt",
    raise_exception=True,
)
@require_http_methods(["GET", "POST"])
def previsualizar_facturacion(request):

    try:
        (
            desde,
            hasta,
            contratistas,
            servicios,
            datos,
        ) = _parametros(request)

    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("bandeja")

    # Selección original de ODT aprobadas.
    seleccion = _odts(
        desde,
        hasta,
        contratistas,
        servicios,
        datos,
    )

    # Contar las que ya están facturadas.
    ya_facturadas = FacturacionODT.objects.filter(
        odt__in=seleccion
    ).count()

    # Excluir las ODT facturadas.
    pendientes = seleccion.filter(
        item_facturacion__isnull=True
    )

    # Resumen exclusivamente de ODT pendientes.
    resumen = _resumen(pendientes)

    # Consultar requisiciones existentes.
    existentes = {
        f.contratista: f.numero_requisicion
        for f in FacturacionContratista.objects.filter(
            periodo__fecha_desde=desde,
            periodo__fecha_hasta=hasta,
        )
    }

    for grupo in resumen:
        grupo["requisicion_existente"] = (
            existentes.get(
                grupo["contratista"],
                "",
            )
        )

    # Confirmar facturación.
    if request.method == "POST":

        if not resumen:
            messages.error(
                request,
                "No existen ODT pendientes y "
                "aprobadas para facturar.",
            )

        else:
            requisiciones = {}
            error_requisicion = False

            for i, grupo in enumerate(resumen):

                valor = request.POST.get(
                    f"requisicion_{i}",
                    "",
                ).strip()

                if len(valor) > 100:
                    messages.error(
                        request,
                        "La requisición de "
                        f'{grupo["contratista"]} '
                        "supera los 100 caracteres.",
                    )
                    error_requisicion = True
                    break

                requisiciones[
                    grupo["contratista"]
                ] = valor

            if not error_requisicion:

                try:
                    with transaction.atomic():

                        # Volver a consultar y bloquear
                        # las ODT pendientes.
                        odts = list(
                            _odts(
                                desde,
                                hasta,
                                contratistas,
                                servicios,
                                datos,
                            )
                            .select_for_update()
                            .filter(
                                item_facturacion__isnull=True
                            )
                        )

                        if not odts:
                            raise ValueError(
                                "Ya no quedan ODT pendientes "
                                "para facturar."
                            )

                        cantidad_esperada = sum(
                            grupo["cantidad"]
                            for grupo in resumen
                        )

                        if len(odts) != cantidad_esperada:
                            raise ValueError(
                                "La selección cambió. "
                                "Actualiza la previsualización."
                            )

                        nombres_actuales = {
                            odt.contratista
                            for odt in odts
                        }

                        if nombres_actuales != set(requisiciones):
                            raise ValueError(
                                "Los contratistas cambiaron. "
                                "Actualiza la previsualización."
                            )

                        # Crear el período si no existe.
                        periodo, _ = (
                            PeriodoFacturacion.objects.get_or_create(
                                fecha_desde=desde,
                                fecha_hasta=hasta,
                                defaults={
                                    "creado_por": request.user,
                                },
                            )
                        )

                        # Bloquear el período durante
                        # la operación cuando el motor
                        # de base de datos lo permita.
                        (
                            PeriodoFacturacion.objects
                            .select_for_update()
                            .get(pk=periodo.pk)
                        )

                        facturaciones = {}

                        # Crear o reutilizar la facturación
                        # del contratista en este período.
                        for nombre, requisicion in (
                            requisiciones.items()
                        ):

                            facturacion, creada = (
                                FacturacionContratista.objects
                                .get_or_create(
                                    periodo=periodo,
                                    contratista=nombre,
                                    defaults={
                                        "numero_requisicion": requisicion,
                                        "creado_por": request.user,
                                    },
                                )
                            )

                            # No sobrescribir requisiciones
                            # previamente registradas.
                            facturaciones[
                                nombre
                            ] = facturacion

                        # Última comprobación de duplicados.
                        if FacturacionODT.objects.filter(
                            odt__in=odts
                        ).exists():
                            raise ValueError(
                                "Se detectaron ODT facturadas "
                                "durante la operación. "
                                "Actualiza la previsualización."
                            )

                        # Guardar únicamente las nuevas ODT.
                        FacturacionODT.objects.bulk_create(
                            [
                                FacturacionODT(
                                    facturacion=facturaciones[
                                        odt.contratista
                                    ],
                                    odt=odt,
                                    servicio_facturado=(
                                        odt.servicio_editado
                                        if odt.servicio_editado is not None
                                        else odt.servicio
                                    ),
                                    monto_facturado=(
                                        odt.valor_pago_editado
                                        if odt.valor_pago_editado is not None
                                        else (
                                            odt.valor_pago_tecnico
                                            if odt.valor_pago_tecnico is not None
                                            else Decimal("0")
                                        )
                                    ),
                                )
                                for odt in odts
                            ],
                            batch_size=500,
                        )

                    messages.success(
                        request,
                        f"Facturación guardada: {len(odts)} "
                        f"ODT de {len(facturaciones)} "
                        "contratistas.",
                    )

                    return redirect(
                        f"{reverse('historial_facturacion')}"
                        f"?periodo={periodo.id}"
                    )

                except (IntegrityError, ValueError) as exc:
                    messages.error(
                        request,
                        "No se guardó la facturación: "
                        f"{exc}",
                    )

    # Totales de la previsualización.
    total = sum(
        (
            grupo["monto"]
            for grupo in resumen
        ),
        Decimal("0"),
    )

    return render(
        request,
        "revisiones/facturacion_periodo.html",
        {
            "desde": desde,
            "hasta": hasta,
            "resumen": resumen,
            "cantidad_odt": sum(
                grupo["cantidad"]
                for grupo in resumen
            ),
            "monto_total": total,
            "ya_facturadas": ya_facturadas,
            "parametros": [
                (k, v)
                for k, valores in datos.lists()
                for v in valores
            ],
        },
    )


@login_required
@permission_required(
    "revisiones.exportar_pagos_sstt",
    raise_exception=True,
)
@require_POST
def actualizar_requisicion(request, facturacion_id):

    facturacion = get_object_or_404(
        FacturacionContratista,
        pk=facturacion_id,
    )

    numero = request.POST.get(
        "numero_requisicion",
        "",
    ).strip()

    if len(numero) > 100:
        messages.error(
            request,
            "La requisición no puede superar "
            "los 100 caracteres.",
        )

    else:
        facturacion.numero_requisicion = numero

        facturacion.save(
            update_fields=[
                "numero_requisicion",
            ]
        )

        if numero:
            messages.success(
                request,
                f"Requisición de {facturacion.contratista} "
                "actualizada correctamente.",
            )
        else:
            messages.success(
                request,
                f"La requisición de {facturacion.contratista} "
                "quedó pendiente.",
            )

    return redirect(
        f"{reverse('historial_facturacion')}"
        f"?periodo={facturacion.periodo_id}"
        f"&contratista={facturacion.id}"
    )



def resumen_costos_periodo(periodo):
    """
    Calcula costos de las ODT efectivamente
    facturadas en el período seleccionado.
    """

    categorias = {
        "correctiva_con_cobro": {
            "nombre": "Mantención correctiva con cobro",
            "monto": Decimal("0"),
            "cantidad": 0,
        },
        "correctiva_sin_cobro": {
            "nombre": "Mantención correctiva sin cobro",
            "monto": Decimal("0"),
            "cantidad": 0,
        },
        "renovacion": {
            "nombre": "Mantención renovación",
            "monto": Decimal("0"),
            "cantidad": 0,
        },
        "preventivo": {
            "nombre": "Mantenimiento preventivo",
            "monto": Decimal("0"),
            "cantidad": 0,
        },
        "otros": {
            "nombre": "Otros servicios",
            "monto": Decimal("0"),
            "cantidad": 0,
        },
    }

    resumen_clientes = {
        "B2B": Decimal("0"),
        "B2C": Decimal("0"),
        "SIN_CLASIFICAR": Decimal("0"),
    }

    items = (
        FacturacionODT.objects
        .filter(facturacion__periodo=periodo)
        .select_related("odt")
    )

    catalogo_clientes = cargar_catalogo_cuentas(
        items.values_list("odt__cuenta_completa", flat=True)
    )

    total = Decimal("0")
    cantidad = 0

    for item in items.iterator(chunk_size=1000):
        monto = item.monto_facturado or Decimal("0")
        servicio = (
            item.servicio_facturado or ""
        ).strip().upper()

        # Normalizar tildes.
        servicio = (
            servicio
            .replace("Á", "A")
            .replace("É", "E")
            .replace("Í", "I")
            .replace("Ó", "O")
            .replace("Ú", "U")
        )

        if servicio == "MANTENCION CORRECTIVA CON COBRO":
            categoria = "correctiva_con_cobro"

        elif servicio == "MANTENCION CORRECTIVA SIN COBRO":
            categoria = "correctiva_sin_cobro"

        elif servicio in (
            "MANTENIMIENTO RENOVACION",
            "MANTENCION RENOVACION",
            "RENOVACION",
        ):
            categoria = "renovacion"

        elif servicio == "MANTENIMIENTO PREVENTIVO":
            categoria = "preventivo"

        else:
            categoria = "otros"

        categorias[categoria]["monto"] += monto
        categorias[categoria]["cantidad"] += 1

        # Clasificación actual del catálogo de cuentas.
        tipo = tipo_cliente_cuenta(item.odt.cuenta_completa, catalogo_clientes)

        resumen_clientes[tipo] += monto

        total += monto
        cantidad += 1

    return {
        "categorias": categorias,
        "clientes": resumen_clientes,
        "total": total,
        "cantidad": cantidad,
    }
