"""Vistas HTTP de bandeja. Sin cambios de reglas de negocio."""
from datetime import date, timedelta
from decimal import Decimal
import time as tiempo
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
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
from ..consultas.pagos import condicion_aprobada, importe_efectivo
from ..consultas.preventivos import asignar_ultimos_preventivos
from ..consultas.servicios import servicio_normalizado
from ..coordinadores_softguard import catalogo_coordinadores, puede_asignar_coordinador
from ..cuentas_utils import cargar_catalogo_cuentas, normalizar_codigo_cuenta, tipo_cliente_cuenta
from ..dominio.pagos import ESTADOS_APROBADOS, OPCIONES_BANDEJA
from ..dominio.servicios import SERVICIOS_PRINCIPALES, nombres_canonicos
from ..facturacion_models import FacturacionODT
from ..models import ODT


SIN_TECNICO_FILTRO = "__SIN_TECNICO__"


def indicador(qs):
    valores = qs.aggregate(
        cantidad=Count("id"),
        monto=Sum(importe_efectivo()),
    )
    return {
        "cantidad": valores["cantidad"],
        "monto": valores["monto"] or Decimal("0"),
    }



def opciones_contratistas(queryset, incluir_sin_tecnico=False):
    valores = list(queryset.order_by("contratista").values_list("contratista", flat=True).distinct())
    nombres = [v for v in valores if v]
    if incluir_sin_tecnico:
        nombres.append(SIN_TECNICO_FILTRO)
    return nombres



@login_required
@permission_required("revisiones.ver_bandeja_sstt", raise_exception=True)
def bandeja(request, por_creacion=False):
    campo_fecha = "fecha_creacion" if por_creacion else "fecha_finalizacion"
    inicio_bandeja = tiempo.perf_counter()
    es_coordinador = es_coordinador_sstt(request.user)
    coordinador_sesion = datos_coordinador(request.user) if es_coordinador else None

    # ==================================================
    # FILTROS DE LA BANDEJA
    # ==================================================

    
   
    # ==================================================
    # FILTROS DE LA BANDEJA
    # ==================================================

    filtros = {
        k: request.GET.get(k, "").strip()
        for k in (
            "estado",
            "revision",
            "coordinador",
            "q",
            "fecha_desde",
            "fecha_hasta",
        )
    }

    # Estado SoftGuard predeterminado
    if "estado" not in request.GET:
        filtros["estado"] = "" if por_creacion else "Finalizado"

    
    
    # ==================================================
    # FECHA INICIAL: DÍA 21 DEL MES ANTERIOR
    # ==================================================

    if "fecha_desde" not in request.GET:
        hoy = timezone.localdate()

        primer_dia_mes_actual = hoy.replace(day=1)
        mes_anterior = primer_dia_mes_actual - timedelta(days=1)

        fecha_desde = mes_anterior.replace(day=21)

        filtros["fecha_desde"] = fecha_desde.isoformat()



    # Fecha hasta: día actual
    if "fecha_hasta" not in request.GET:
        filtros["fecha_hasta"] = (
            timezone.localdate().isoformat()
        )

    # ==================================================
    # SERVICIOS PREDETERMINADOS
    # ==================================================

    servicios_predeterminados = list(SERVICIOS_PRINCIPALES)

    servicios_seleccionados = request.GET.getlist(
        "servicios"
    )

    if not request.GET and not por_creacion:
        servicios_seleccionados = (
            servicios_predeterminados.copy()
        )

    # ==================================================
    # CONTRATISTAS SELECCIONADOS
    # ==================================================

    contratistas_seleccionados = request.GET.getlist(
        "contratista"
    )


   
    contratistas_disponibles = ODT.objects.all()
    if filtros["estado"]:
        contratistas_disponibles = contratistas_disponibles.filter(estado_softguard=filtros["estado"])

    # Filtrar por servicios seleccionados.
    if servicios_seleccionados:
        contratistas_disponibles = contratistas_disponibles.filter(
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

            contratistas_disponibles = contratistas_disponibles.filter(
                **{
                    f"{campo_fecha}__date__{operador}":
                        fecha_valida
                }
            )

    contratistas_disponibles = limitar_odts_coordinador(request, contratistas_disponibles)

    contratistas_disponibles = opciones_contratistas(
        contratistas_disponibles, incluir_sin_tecnico=por_creacion
    )

    seleccion_contratistas_explicita = (
        "contratistas_filtrados" in request.GET or "contratista" in request.GET
    )
    if not seleccion_contratistas_explicita:
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
                messages.warning(
                    request,
                    f"Fecha inválida: {valor}",
                )

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
    if "numero_odt" in request.GET:
        numero_exacto = request.GET.get("numero_odt", "").strip()
        if numero_exacto.isascii() and numero_exacto.isdigit() and len(numero_exacto) <= 10:
            registros = registros.filter(numero=int(numero_exacto))
        else:
            registros = registros.none()

    if es_coordinador:
        filtros["coordinador"] = coordinador_sesion["usuario"]
        registros = limitar_odts_coordinador(request, registros)

    coordinador_seleccionado = filtros["coordinador"]

    coordinadores_validos = {
        "jtapia",
        "jbicz",
        "yramirez",
        "rsilva",
        "SIN_IDENTIFICAR",
    }

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



    
    # ==================================================
    # INDICADORES OPERATIVOS DE CORRECCIONES
    # ==================================================

    # Se reutiliza el queryset "registros", que ya contiene
    # los filtros de la bandeja, incluido el coordinador.

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
            "coordinadores_asignables": list(catalogo_coordinadores().values()),
            "servicios_principales": SERVICIOS_PRINCIPALES,
            

            "kpi_odt_modificadas": kpi_odt_modificadas,
            "kpi_servicios_corregir": kpi_servicios_corregir,
            "kpi_montos_corregir": kpi_montos_corregir,

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

            "total": total,
            "aprobadas": aprobadas,
            "en_revision": en_revision,
            "rechazadas": rechazadas,
            "por_revisar": por_revisar,
            "observadas": observadas,

            "indicadores": {
                "total": total,
                "aprobadas": aprobadas,
                "en_revision": en_revision,
                "rechazadas": rechazadas,
            },
            "mantencion_con_cobro": mantencion_con_cobro,
            "mantencion_sin_cobro": mantencion_sin_cobro,
            "renovacion": renovacion,
            "mantenimiento_preventivo": mantenimiento_preventivo,
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

