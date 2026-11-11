"""Vistas HTTP de bandeja. Sin cambios de reglas de negocio."""
import time as tiempo
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
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
from ..coordinadores_softguard import catalogo_coordinadores, puede_asignar_coordinador
from ..dominio.pagos import OPCIONES_BANDEJA
from ..dominio.servicios import SERVICIOS_PRINCIPALES
from ..models import ODT
from ..consultas.catalogos_bandeja import servicios_disponibles, estados_disponibles, filtrar_opciones_ajax
from ..consultas.filas_bandeja import paginar_filas, cargar_complementos
from ..presentacion.filas_bandeja import preparar_filas

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
        filtros["coordinador"] = coordinador_sesion["usuario"] if coordinador_sesion else ""
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

    pagina = paginar_filas(registros, request.GET.get("page"), request.GET.get("ubicar_odt"),
                           priorizar_correcciones=not por_creacion,
                           filas_guardadas=request.GET.get("filas_guardadas"))
    filas = pagina.object_list
    coordinadores_pagina = coordinadores_para_mostrar(request, [odt.numero for odt in filas])
    complementos = cargar_complementos(filas)
    pagina.object_list = preparar_filas(
        filas, coordinadores_pagina=coordinadores_pagina,
        facturadas=complementos.facturadas, catalogo=complementos.catalogo,
        puede_procesar=es_coordinador or request.user.has_perm("revisiones.editar_odt_sstt"),
        puede_asignar=puede_asignar_coordinador(request.user),
    )
    print(
        f"[SSTT] Paginación y obtención de ODT: "
        f"{tiempo.perf_counter() - inicio_paginacion:.2f} s"
    )

    parametros = request.GET.copy()
    parametros.pop("page", None)
    parametros.pop("ubicar_odt", None)
    parametros.pop("filas_guardadas", None)
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

    servicios = servicios_disponibles()

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
            "destacar_monto_cero": (not es_coordinador and request.user.has_perm("revisiones.revisar_pago_sstt")
                                     and (request.user.is_superuser or request.user.groups.filter(name="Supervisor").exists())),
            "coordinador_sesion": coordinador_sesion,
            "coordinadores_asignables": list(catalogo.values()),
            "servicios_principales": SERVICIOS_PRINCIPALES,
            

            "kpi_odt_modificadas": operativos["kpi_odt_modificadas"],
            "kpi_servicios_corregir": operativos["kpi_servicios_corregir"],
            "kpi_montos_corregir": operativos["kpi_montos_corregir"],

            "estados": estados_disponibles(),

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
            "acuerdo_comercial": financieros["acuerdo_comercial"],
            "presupuesto": financieros["presupuesto"],
            "nueva_instalacion_cruzverde": financieros["nueva_instalacion_cruzverde"],
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

    registros = filtrar_opciones_ajax(
        ODT.objects.all(), campo_fecha=campo_fecha,
        fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
        estado=estado, servicios=servicios,
    )

    registros = limitar_odts_coordinador(request, registros)

    contratistas = opciones_contratistas(
        registros, incluir_sin_tecnico=(campo_fecha == "fecha_creacion")
    )

    return JsonResponse({
        "contratistas": contratistas
    })

