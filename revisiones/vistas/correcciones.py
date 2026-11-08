"""Vistas HTTP de correcciones. Sin cambios de reglas de negocio."""
from decimal import Decimal
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import render
from ..acceso_coordinadores import coordinadores_en_peticion, coordinadores_para_mostrar
from ..consultas.pagos import importe_efectivo
from ..coordinadores_softguard import catalogo_coordinadores
from ..models import ODT


@login_required
@permission_required(
    "revisiones.ver_bandeja_sstt",
    raise_exception=True
)
@login_required
@permission_required("revisiones.ver_bandeja_sstt", raise_exception=True)
def odt_modificadas(request):
    """Listado de cambios y comparación con la última sincronización SoftGuard."""
    registros = (
        ODT.objects.select_related("revision", "seguimiento_correccion")
        .filter(
            Q(seguimiento_correccion__isnull=False)
            | Q(servicio_editado__isnull=False)
            | Q(valor_pago_editado__isnull=False)
        )
        .order_by("-numero")
    )

    coordinador_seleccionado = request.GET.get("coordinador", "").strip()
    tipo = request.GET.get("tipo", "").strip()
    correccion = request.GET.get("correccion", "").strip()
    q = request.GET.get("q", "").strip()

    if tipo == "MONTO":
        registros = registros.filter(valor_pago_editado__isnull=False)
    elif tipo == "SERVICIO":
        registros = registros.filter(servicio_editado__isnull=False)
    elif tipo == "AMBOS":
        registros = registros.filter(
            servicio_editado__isnull=False,
            valor_pago_editado__isnull=False,
        )

    if q:
        condicion = (
            Q(tecnico__icontains=q)
            | Q(contratista__icontains=q)
            | Q(cuenta_completa__icontains=q)
        )
        numero_buscado = q.replace(".", "").replace(" ", "")
        if numero_buscado.isdigit():
            condicion |= Q(numero=int(numero_buscado))
        registros = registros.filter(condicion)

    # Filtrar por estado persistente (sin perder ODT actualizadas).
    # Los registros anteriores se inicializan con el comando incluido.
    if correccion in ("PENDIENTE", "EN_PROCESO", "ACTUALIZADA"):
        registros = registros.filter(seguimiento_correccion__estado=correccion)

    if coordinador_seleccionado:
        responsables = coordinadores_en_peticion(
            request, registros.order_by().values_list("numero", flat=True).iterator(),
        )
        numeros_filtrados = [
            numero for numero, info in responsables.items()
            if (not info.get("identificado", False) if coordinador_seleccionado == "SIN_IDENTIFICAR"
                else info.get("usuario") == coordinador_seleccionado)
        ]
        registros = registros.filter(numero__in=numeros_filtrados)

    resumen = registros.aggregate(
        cantidad=Count("pk"),
        monto_original=Sum("valor_pago_tecnico"),
        monto_corregido=Sum(importe_efectivo()),
    )
    monto_original = resumen["monto_original"] or Decimal("0")
    monto_corregido = resumen["monto_corregido"] or Decimal("0")

    pagina = Paginator(registros, 50).get_page(request.GET.get("page"))
    filas = []

    coordinadores_pagina = coordinadores_para_mostrar(request, [o.numero for o in pagina.object_list])

    for odt in pagina.object_list:
        coordinador = coordinadores_pagina[odt.numero]
        monto_original_fila = odt.valor_pago_tecnico or Decimal("0")
        cambio_monto = odt.valor_pago_editado is not None
        cambio_servicio = odt.servicio_editado is not None
        monto_actual = (
            odt.valor_pago_editado if cambio_monto else monto_original_fila
        )
        servicio_actual = (
            odt.servicio_editado if cambio_servicio else odt.servicio
        )

        seguimiento = getattr(odt, "seguimiento_correccion", None)
        estado_correccion = seguimiento.estado if seguimiento else "PENDIENTE"
        if seguimiento:
            cambio_monto = seguimiento.corrige_monto
            cambio_servicio = seguimiento.corrige_servicio
            monto_actual = seguimiento.monto_objetivo
            servicio_actual = seguimiento.servicio_objetivo

        filas.append({
            "numero": odt.numero,
            "coordinador": coordinador.get("nombre", "Sin identificar"),
            "coordinador_identificado": coordinador.get("identificado", False),
            "contratista": odt.contratista,
            "tecnico": odt.tecnico,
            "cuenta": odt.cuenta_completa,
            "fecha_finalizacion": odt.fecha_finalizacion,
            "servicio_original": odt.servicio,
            "servicio_actual": servicio_actual,
            "monto_original": monto_original_fila,
            "monto_actual": monto_actual,
            "cambio_monto": cambio_monto,
            "cambio_servicio": cambio_servicio,
            "estado_correccion": estado_correccion,
        })

    parametros = request.GET.copy()
    parametros.pop("page", None)
    coordinadores = [
        {"usuario": datos["usuario"], "nombre": datos["nombre"]}
        for datos in catalogo_coordinadores().values()
    ]

    return render(request, "revisiones/odt_modificadas.html", {
        "filas": filas,
        "pagina": pagina,
        "coordinadores": coordinadores,
        "coordinador_seleccionado": coordinador_seleccionado,
        "tipo_seleccionado": tipo,
        "correccion_seleccionada": correccion,
        "q": q,
        "querystring": parametros.urlencode(),
        "cantidad": resumen["cantidad"],
        "monto_original": monto_original,
        "monto_corregido": monto_corregido,
        "diferencia_total": monto_corregido - monto_original,
    })

