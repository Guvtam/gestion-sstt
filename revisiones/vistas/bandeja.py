"""Vistas HTTP de bandeja. Sin cambios de reglas de negocio."""
import time as tiempo
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from ..acceso_coordinadores import (
    datos_coordinador,
    es_coordinador_sstt,
    limitar_odts_coordinador,
    coordinadores_en_peticion,
    coordinadores_para_mostrar,
)
from ..consultas.preventivos import asignar_ultimos_preventivos
from ..coordinadores_softguard import catalogo_coordinadores, puede_asignar_coordinador
from ..cuentas_utils import cargar_catalogo_cuentas, normalizar_codigo_cuenta, tipo_cliente_cuenta
from ..dominio.pagos import OPCIONES_BANDEJA
from ..dominio.servicios import SERVICIOS_PRINCIPALES
from ..facturacion_models import FacturacionODT
from ..models import ODT

from ..dominio.filtros_bandeja import SIN_TECNICO_FILTRO, leer_seleccion
from ..consultas.filtros_bandeja import filtrar_disponibles, filtrar_tabla, opciones_contratistas
from ..consultas.indicadores_bandeja import indicador, indicadores_financieros, indicadores_operativos


@login_required
@permission_required("revisiones.ver_bandeja_sstt", raise_exception=True)
def bandeja(request, por_creacion=False):
    campo_fecha = "fecha_creacion" if por_creacion else "fecha_finalizacion"
    inicio_bandeja = tiempo.perf_counter()
    es_coordinador = es_coordinador_sstt(request.user)
    coordinador_sesion = datos_coordinador(request.user) if es_coordinador else None

    seleccion = leer_seleccion(
        request.GET, por_creacion=por_creacion, hoy=timezone.localdate(),
    )
    filtros = seleccion.filtros()
    servicios_seleccionados = list(seleccion.servicios)
    contratistas_seleccionados = list(seleccion.contratistas)

    contratistas_disponibles = ODT.objects.all()
    contratistas_disponibles = filtrar_disponibles(
        contratistas_disponibles, filtros=filtros,
        servicios_seleccionados=servicios_seleccionados, campo_fecha=campo_fecha,
    )

    contratistas_disponibles = limitar_odts_coordinador(request, contratistas_disponibles)

    contratistas_disponibles = opciones_contratistas(
        contratistas_disponibles, incluir_sin_tecnico=por_creacion
    )

    if not seleccion.contratistas_explicitos:
        contratistas_seleccionados = list(contratistas_disponibles)

    # ==================================================
    # CONTADOR DE INCIDENCIAS - ÚLTIMOS 90 DÍAS
    # Misma cuenta + mismo contratista
    # ==================================================

    from ..indicadores_odt import con_indicadores_odt
    registros = con_indicadores_odt(
        ODT.objects.select_related("revision", "seguimiento_correccion")
    )

    # ==================================================
    # FILTROS DE LA TABLA
    # ==================================================

    registros = filtrar_tabla(
        registros, filtros=filtros, servicios_seleccionados=servicios_seleccionados,
        contratistas_seleccionados=contratistas_seleccionados, campo_fecha=campo_fecha,
        por_creacion=por_creacion, numero_exacto=seleccion.numero_exacto,
        avisar_fecha=lambda valor: messages.warning(request, f"Fecha inválida: {valor}"),
    )

    if es_coordinador:
        filtros["coordinador"] = coordinador_sesion["usuario"]
        registros = limitar_odts_coordinador(request, registros)

    coordinador_seleccionado = filtros["coordinador"]
    catalogo = catalogo_coordinadores()

    coordinadores_validos = {d["usuario"] for d in catalogo.values()} | {"SIN_IDENTIFICAR"}

    if coordinador_seleccionado and not es_coordinador:

        if coordinador_seleccionado not in coordinadores_validos:
            registros = registros.none()

        else:
            responsables = coordinadores_en_peticion(
                request, registros.order_by().values_list("numero", flat=True).iterator(chunk_size=500),
            )
            numeros_filtrados = [
                numero for numero, info in responsables.items()
                if (not info.get("identificado", False) if coordinador_seleccionado == "SIN_IDENTIFICAR"
                    else info.get("usuario") == coordinador_seleccionado)
            ]
            registros = registros.filter(numero__in=numeros_filtrados)


    # ==================================================
    # INDICADORES FINANCIEROS OPTIMIZADOS
    # ==================================================

    print(
        f"[SSTT] Construcción de consultas: "
        f"{tiempo.perf_counter() - inicio_bandeja:.2f} s"
    )

    inicio_indicadores = tiempo.perf_counter()

    financieros = indicadores_financieros(registros)
    operativos = indicadores_operativos(registros)

    # ==================================================
    # PAGINACIÓN
    # ==================================================
    print(
        f"[SSTT] Indicadores financieros: "
        f"{tiempo.perf_counter() - inicio_indicadores:.2f} s"
    )

    inicio_paginacion = tiempo.perf_counter()

    # Paginación ligera: primero obtenemos los ID
    # de las 50 ODT correspondientes a la página.

    registros_base = (
        registros
        .order_by(
            "cuenta_completa",
            "codigo_tecnico",
            "fecha_finalizacion",
            "-numero",
        )
        .values_list("pk", flat=True)
    )

    pagina = Paginator(
        registros_base,
        50
    ).get_page(request.GET.get("page"))

    ids_pagina = list(pagina.object_list)

    # Ahora calculamos SLA, incidencias y preventivos
    # solamente para las ODT seleccionadas.

    registros_pagina = list(
        registros.filter(
            pk__in=ids_pagina
        )
    )

    orden_ids = {
        pk: posicion
        for posicion, pk in enumerate(ids_pagina)
    }

    registros_pagina.sort(
        key=lambda odt: orden_ids[odt.pk]
    )

    pagina.object_list = asignar_ultimos_preventivos(registros_pagina)

    
    # ==================================================
    # COORDINADOR DE LAS ODT VISIBLES
    # ==================================================

    coordinadores_pagina = coordinadores_para_mostrar(request, [o.numero for o in pagina.object_list])

    for odt in pagina.object_list:
        seguimiento = getattr(odt, "seguimiento_correccion", None)
        odt.estado_modificacion = (
            seguimiento.estado if seguimiento else
            ("PENDIENTE" if odt.servicio_editado is not None or odt.valor_pago_editado is not None else "")
        )
        odt.puede_procesar_modificacion = (
            odt.estado_modificacion == "PENDIENTE"
            and (es_coordinador or request.user.has_perm("revisiones.editar_odt_sstt"))
        )
        odt.permite_asignar_coordinador = False
        info = coordinadores_pagina[odt.numero]
        odt.coordinador_nombre = info.get("nombre") or "Sin identificar"
        odt.coordinador_identificado = bool(info.get("identificado", False))
        odt.permite_asignar_coordinador = (
            info.get("disponible", True) and not odt.coordinador_identificado
            and puede_asignar_coordinador(request.user)
        )

    # ==================================================
    # IDENTIFICAR ODT FACTURADAS Y RECHAZADAS
    # Solo las 50 ODT visibles en la página.
    # ==================================================

    ids_facturadas = set(
        FacturacionODT.objects.filter(
            odt_id__in=ids_pagina
        ).values_list("odt_id", flat=True)
    )

    for odt in pagina.object_list:

        odt.esta_facturada = (
            odt.pk in ids_facturadas
        )

        estado_revision = (
            odt.revision.estado
            if hasattr(odt, "revision")
            else None
        )

        odt.esta_rechazada = (
            estado_revision == "RECHAZADA"
        )

        odt.esta_bloqueada = (
            odt.esta_facturada
            or odt.esta_rechazada
        )


    # CECO y clasificación del catálogo para las 50 ODT visibles.
    # Se consulta una sola vez por página, sin subconsultas adicionales.
    print(
        f"[SSTT] Paginación y obtención de ODT: "
        f"{tiempo.perf_counter() - inicio_paginacion:.2f} s"
    )

    catalogo_pagina = cargar_catalogo_cuentas(odt.cuenta_completa for odt in pagina.object_list)

    for odt in pagina.object_list:
        codigo = normalizar_codigo_cuenta(odt.cuenta_completa)
        cuenta = catalogo_pagina.get(codigo)
        odt.codigo_cuenta_catalogo = codigo
        odt.ceco_catalogo = cuenta.ceco if cuenta else ""
        odt.tipo_cliente_catalogo = tipo_cliente_cuenta(odt.cuenta_completa, catalogo_pagina)
        odt.ceco_requiere_revision = (
            cuenta.requiere_revision_ceco if cuenta else False
        )
        odt.cuenta_en_catalogo = cuenta is not None

    
    parametros = request.GET.copy()
    parametros.pop("page", None)
    parametros["contratistas_filtrados"] = "1"
    parametros.setlist("contratista", contratistas_seleccionados)

    # Conservar los filtros efectivos en la paginación.
    parametros["estado"] = filtros["estado"]
    parametros["fecha_desde"] = filtros["fecha_desde"]
    parametros["fecha_hasta"] = filtros["fecha_hasta"]

    if not request.GET:
        parametros.setlist(
            "servicios",
            servicios_seleccionados
        )


    inicio_servicios = tiempo.perf_counter()
    # ==================================================
    # CATÁLOGO DE SERVICIOS
    # ==================================================

    servicios_originales = set(
        ODT.objects
        .exclude(servicio__isnull=True)
        .exclude(servicio="")
        .order_by()
        .values_list("servicio", flat=True)
        .distinct()
    )

    servicios_editados = set(
        ODT.objects
        .exclude(servicio_editado__isnull=True)
        .exclude(servicio_editado="")
        .order_by()
        .values_list("servicio_editado", flat=True)
        .distinct()
    )

    

    servicios = sorted(
        servicios_originales | servicios_editados
    )

    print(
        f"[SSTT] Catálogo de servicios: "
        f"{tiempo.perf_counter() - inicio_servicios:.2f} s"
    )

    print(
        f"[RENDIMIENTO SSTT] Bandeja: "
        f"{tiempo.perf_counter() - inicio_bandeja:.2f} segundos"
    )

    
    # ==================================================
    # CONTRATISTAS DISPONIBLES SEGÚN FECHAS Y SERVICIOS
    # ==================================================

    # Identificar usuarios con rol de coordinador.
    # El grupo debe existir en Django Admin.
    es_coordinador = es_coordinador_sstt(request.user)


    # ==================================================
    # RENDERIZAR BANDEJA
    # ==================================================

    return render(
        request,
        "revisiones/bandeja.html",
        {
            "por_creacion": por_creacion,
            "bandeja_url": "bandeja_creacion" if por_creacion else "bandeja",
            "registros": pagina.object_list,
            "pagina": pagina,
            "page_obj": pagina,
            "querystring": parametros.urlencode(),
            "filtros": filtros,

            "contratistas": contratistas_disponibles,
            "es_coordinador": es_coordinador,
            "coordinador_sesion": coordinador_sesion,
            "coordinadores_asignables": list(catalogo.values()),
            "servicios_principales": SERVICIOS_PRINCIPALES,
            

            "kpi_odt_modificadas": operativos["kpi_odt_modificadas"],
            "kpi_servicios_corregir": operativos["kpi_servicios_corregir"],
            "kpi_montos_corregir": operativos["kpi_montos_corregir"],

            "estados": (
                ODT.objects
                .exclude(estado_softguard="")
                .order_by("estado_softguard")
                .values_list("estado_softguard", flat=True)
                .distinct()
            ),

            "servicios": servicios,
            "servicios_seleccionados": servicios_seleccionados,
            "contratistas_seleccionados": contratistas_seleccionados,
            "opciones": OPCIONES_BANDEJA,

            "total": financieros["total"],
            "aprobadas": financieros["aprobadas"],
            "en_revision": financieros["en_revision"],
            "rechazadas": financieros["rechazadas"],
            "por_revisar": financieros["por_revisar"],
            "observadas": financieros["observadas"],

            "indicadores": {
                "total": financieros["total"],
                "aprobadas": financieros["aprobadas"],
                "en_revision": financieros["en_revision"],
                "rechazadas": financieros["rechazadas"],
            },
            "mantencion_con_cobro": financieros["mantencion_con_cobro"],
            "mantencion_sin_cobro": financieros["mantencion_sin_cobro"],
            "renovacion": financieros["renovacion"],
            "mantenimiento_preventivo": financieros["mantenimiento_preventivo"],
        },
    )


@login_required
@permission_required("revisiones.ver_bandeja_sstt", raise_exception=True)
def bandeja_creacion(request):
    return bandeja(request, por_creacion=True)


@login_required
@permission_required("revisiones.ver_bandeja_sstt", raise_exception=True)
def contratistas_disponibles_ajax(request):
    campo_fecha = "fecha_creacion" if request.GET.get("campo_fecha") == "creacion" else "fecha_finalizacion"

    fecha_desde = request.GET.get("fecha_desde", "")
    fecha_hasta = request.GET.get("fecha_hasta", "")
    estado = request.GET.get("estado", "")
    servicios = request.GET.getlist("servicios")

    registros = ODT.objects.all()

    # Fecha de finalización
    if fecha_desde:
        registros = registros.filter(
            **{f"{campo_fecha}__date__gte": fecha_desde}
        )

    if fecha_hasta:
        registros = registros.filter(
            **{f"{campo_fecha}__date__lte": fecha_hasta}
        )

    # Estado SoftGuard
    if estado:
        registros = registros.filter(
            estado_softguard=estado
        )

    # Servicios, considerando modificaciones
    if servicios:
        registros = registros.filter(
            Q(
                servicio_editado__isnull=True,
                servicio__in=servicios
            )
            |
            Q(
                servicio_editado__in=servicios
            )
        )

    registros = limitar_odts_coordinador(request, registros)

    contratistas = opciones_contratistas(
        registros, incluir_sin_tecnico=(campo_fecha == "fecha_creacion")
    )

    return JsonResponse({
        "contratistas": contratistas
    })

