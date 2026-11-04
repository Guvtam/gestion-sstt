
from datetime import date, timedelta
import time as tiempo
from decimal import Decimal, InvalidOperation
from .facturacion_models import FacturacionODT

from django.utils import timezone


from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import (
    Q, Sum, Count, DecimalField, OuterRef, Subquery
)
from django.db.models.functions import Coalesce
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from .acceso_coordinadores import es_coordinador_sstt, datos_coordinador, limitar_odts_coordinador, coordinador_visible
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import ODT, Revision, EventoRevision, CatalogoCuenta, CorreccionODT, EventoCorreccionODT
from .correcciones import registrar_cambio_manual
from .cuentas_utils import normalizar_codigo_cuenta
from .servicios_sql import consultar_historial_odt
from .coordinadores_softguard import (identificar_coordinador_odt, puede_asignar_coordinador,
    identificar_coordinador_softguard, COORDINADORES_SOFTGUARD)
from .models import AsignacionCoordinadorODT

from django.db.models import (
   
    F,
    ExpressionWrapper,
    DurationField,
    Case,
    When,
    Value,
    CharField,
    DateTimeField,
    IntegerField,
)

# Estados anteriores que ahora se consideran aprobados por defecto.
ESTADOS_APROBADOS = ("APROBADA", "POR_REVISAR")

# Estados que se pueden seleccionar en la nueva bandeja.
OPCIONES_BANDEJA = (
    ("APROBADA", "Aprobado"),
    ("EN_REVISION", "En revisión"),
    ("RECHAZADA", "Rechazado"),
)


def importe_efectivo():
    """Monto corregido si existe; en otro caso, monto original."""
    return Coalesce(
        "valor_pago_editado",
        "valor_pago_tecnico",
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )


def condicion_aprobada():
    """
    Las ODT sin revisión o con estado POR_REVISAR anterior
    se consideran aprobadas en la nueva lógica.
    """
    return (
        Q(revision__isnull=True)
        | Q(revision__estado__in=ESTADOS_APROBADOS)
    )



def odt_facturada(odt):
    """Comprueba si la ODT ya tiene facturación registrada."""
    return FacturacionODT.objects.filter(odt=odt).exists()


def odt_rechazada(odt):
    """Comprueba si la ODT tiene un rechazo definitivo."""
    return Revision.objects.filter(
        odt=odt,
        estado="RECHAZADA",
    ).exists()


def error_odt_bloqueada(odt):
    """Devuelve el motivo del bloqueo, si corresponde."""
    if odt_facturada(odt):
        return (
            "La ODT ya está facturada y no permite "
            "modificaciones."
        )

    if odt_rechazada(odt):
        return (
            "La ODT está rechazada definitivamente "
            "y no permite modificaciones."
        )

    return None


def indicador(qs):
    valores = qs.aggregate(
        cantidad=Count("id"),
        monto=Sum(importe_efectivo()),
    )
    return {
        "cantidad": valores["cantidad"],
        "monto": valores["monto"] or Decimal("0"),
    }



@login_required
@permission_required("revisiones.ver_bandeja_sstt", raise_exception=True)
def bandeja(request):
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
        filtros["estado"] = "Finalizado"

    
    
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

    servicios_predeterminados = [
        "MANTENCION CORRECTIVA CON COBRO",
        "MANTENCION CORRECTIVA SIN COBRO",
        "MANTENIMIENTO PREVENTIVO",
        "MANTENIMIENTO RENOVACIÓN",
    ]

    servicios_seleccionados = request.GET.getlist(
        "servicios"
    )

    if not request.GET:
        servicios_seleccionados = (
            servicios_predeterminados.copy()
        )

    # ==================================================
    # CONTRATISTAS SELECCIONADOS
    # ==================================================

    contratistas_seleccionados = request.GET.getlist(
        "contratista"
    )


   
    # ==================================================
    # CONTADOR DE INCIDENCIAS - ÚLTIMOS 90 DÍAS
    # Misma cuenta + mismo contratista
    # ==================================================

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
        ODT.objects
        .select_related("revision", "seguimiento_correccion")

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

    # ==================================================
    # FILTROS DE LA TABLA
    # ==================================================

    # Contratista.
    if contratistas_seleccionados:
        registros = registros.filter(contratista__in=contratistas_seleccionados)

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
                        f"fecha_finalizacion__date__{operador}":
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
            numeros_filtrados = []

            numeros_candidatos = registros.order_by().values_list(
                "numero",
                flat=True
            ).iterator(chunk_size=500)

            for numero in numeros_candidatos:

                try:
                    info = identificar_coordinador_odt(numero)

                except Exception:
                    # No atribuir un coordinador cuando
                    # falla la consulta del historial.
                    raise

                if coordinador_seleccionado == "SIN_IDENTIFICAR":
                    coincide = not info.get("identificado", False)
                else:
                    coincide = (
                        info.get("usuario") == coordinador_seleccionado
                    )

                if coincide:
                    numeros_filtrados.append(numero)

            registros = registros.filter(
                numero__in=numeros_filtrados
            )



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
    base_indicadores = registros.order_by().values(
        "pk",
        "valor_pago_tecnico",
        "valor_pago_editado",
        "revision__estado",
    )
    
    # Clasificación de mantenciones según el servicio efectivo.
    # Se prioriza el servicio corregido manualmente.

    condicion_mantencion_con_cobro = (
        Q(servicio_editado__iexact="MANTENCION CORRECTIVA CON COBRO")
        | (
            Q(servicio_editado__isnull=True)
            & Q(servicio__iexact="MANTENCION CORRECTIVA CON COBRO")
        )
    )

    condicion_mantencion_sin_cobro = (
        Q(servicio_editado__iexact="MANTENCION CORRECTIVA SIN COBRO")
        | (
            Q(servicio_editado__isnull=True)
            & Q(servicio__iexact="MANTENCION CORRECTIVA SIN COBRO")
        )
    )


    
    # Mantenimiento renovación.
    # Se prioriza el servicio editado sobre el original.

    nombres_renovacion = (
        "RENOVACION",
        "RENOVACIÓN",
        "MANTENIMIENTO RENOVACION",
        "MANTENIMIENTO RENOVACIÓN",
        "MANTENCION RENOVACION",
        "MANTENCIÓN RENOVACIÓN",
    )

    condicion_renovacion = (
        Q(servicio_editado__in=nombres_renovacion)
        | (
            Q(servicio_editado__isnull=True)
            & Q(servicio__in=nombres_renovacion)
        )
    )


    condicion_mantenimiento_preventivo = (
        Q(servicio_editado__iexact="MANTENIMIENTO PREVENTIVO")
        | (
            Q(servicio_editado__isnull=True)
            & Q(servicio__iexact="MANTENIMIENTO PREVENTIVO")
        )
    )

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

    pagina.object_list = registros_pagina

    
    # ==================================================
    # COORDINADOR DE LAS ODT VISIBLES
    # ==================================================

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
        try:
            info = identificar_coordinador_odt(odt.numero)

            odt.coordinador_nombre = (
                info.get("nombre") or "Sin identificar"
            )
            odt.coordinador_identificado = bool(
                info.get("identificado", False)
            )
            odt.permite_asignar_coordinador = (
                not odt.coordinador_identificado and puede_asignar_coordinador(request.user)
            )

        except Exception:
            odt.coordinador_nombre = "No disponible"
            odt.coordinador_identificado = False


    
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
    codigos_pagina = {
        normalizar_codigo_cuenta(odt.cuenta_completa)
        for odt in pagina.object_list
    }
    codigos_pagina.discard("")

    print(
        f"[SSTT] Paginación y obtención de ODT: "
        f"{tiempo.perf_counter() - inicio_paginacion:.2f} s"
    )

    catalogo_pagina = {
        cuenta.codigo_cuenta: cuenta
        for cuenta in CatalogoCuenta.objects.filter(
            codigo_cuenta__in=codigos_pagina
        )
    }

    for odt in pagina.object_list:
        codigo = normalizar_codigo_cuenta(odt.cuenta_completa)
        cuenta = catalogo_pagina.get(codigo)
        odt.codigo_cuenta_catalogo = codigo
        odt.ceco_catalogo = cuenta.ceco if cuenta else ""
        odt.tipo_cliente_catalogo = (
            cuenta.tipo_cliente
            if cuenta
            else "SIN_CLASIFICAR"
        )
        odt.ceco_requiere_revision = (
            cuenta.requiere_revision_ceco if cuenta else False
        )
        odt.cuenta_en_catalogo = cuenta is not None

    
    parametros = request.GET.copy()
    parametros.pop("page", None)

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

    contratistas_disponibles = ODT.objects.all()

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
                    f"fecha_finalizacion__date__{operador}":
                        fecha_valida
                }
            )

    contratistas_disponibles = limitar_odts_coordinador(request, contratistas_disponibles)

    # Obtener únicamente contratistas con ODT coincidentes.
    contratistas_disponibles = (
        contratistas_disponibles
        .exclude(contratista__isnull=True)
        .exclude(contratista="")
        .order_by("contratista")
        .values_list("contratista", flat=True)
        .distinct()
    )

    
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
            "registros": pagina.object_list,
            "pagina": pagina,
            "page_obj": pagina,
            "querystring": parametros.urlencode(),
            "filtros": filtros,

            "contratistas": contratistas_disponibles,
            "es_coordinador": es_coordinador,
            "coordinador_sesion": coordinador_sesion,
            "coordinadores_asignables": list(COORDINADORES_SOFTGUARD.values()),
            

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
def contratistas_disponibles_ajax(request):

    fecha_desde = request.GET.get("fecha_desde", "")
    fecha_hasta = request.GET.get("fecha_hasta", "")
    estado = request.GET.get("estado", "")
    servicios = request.GET.getlist("servicios")

    registros = limitar_odts_coordinador(request, ODT.objects.all())

    # Fecha de finalización
    if fecha_desde:
        registros = registros.filter(
            fecha_finalizacion__date__gte=fecha_desde
        )

    if fecha_hasta:
        registros = registros.filter(
            fecha_finalizacion__date__lte=fecha_hasta
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

    contratistas = list(
        registros
        .exclude(contratista__isnull=True)
        .exclude(contratista="")
        .order_by("contratista")
        .values_list("contratista", flat=True)
        .distinct()
    )

    return JsonResponse({
        "contratistas": contratistas
    })



@login_required
@permission_required("revisiones.ver_bandeja_sstt", raise_exception=True)
def detalle(request, numero):
    odt = get_object_or_404(
        ODT.objects.select_related("revision"),
        numero=numero,
    )

    return render(
        request,
        "revisiones/detalle.html",
        {
            "odt": odt,
            "opciones": Revision.ESTADOS,
            "eventos": (
                odt.eventos_revision
                .select_related("usuario")[:30]
            ),
        },
    )



@login_required
@permission_required(
    "revisiones.revisar_pago_sstt",
    raise_exception=True,
)



@require_POST
def acciones(request):
    """
    Revisión múltiple conservada para compatibilidad.
    Impide modificar ODT facturadas o rechazadas.
    """

    ids = request.POST.getlist("odts")
    nuevo = request.POST.get("nuevo_estado", "").strip()
    comentario = request.POST.get("comentario", "").strip()

    validos = {
        "APROBADA": "Aprobado",
        "EN_REVISION": "En revisión",
        "RECHAZADA": "Rechazado",
    }

    if nuevo not in validos:
        messages.error(request, "Estado de revisión inválido.")
        return redirect("bandeja")

    if nuevo in ("EN_REVISION", "RECHAZADA") and not comentario:
        messages.error(
            request,
            "Debes indicar el motivo del cambio de estado.",
        )
        return redirect("bandeja")

    numeros = list({
        int(x) for x in ids if x.isdigit() and int(x) > 0
    })

    if not numeros or len(numeros) > 300:
        messages.error(
            request,
            "Selecciona entre 1 y 300 ODT.",
        )
        return redirect("bandeja")

    with transaction.atomic():

        odts = list(
            ODT.objects
            .select_for_update()
            .filter(numero__in=numeros)
            .order_by("numero")
        )

        if len(odts) != len(numeros):
            messages.error(
                request,
                "Algunas ODT seleccionadas no existen.",
            )
            return redirect("bandeja")

        # Validar todas antes de guardar cambios.
        for odt in odts:
            bloqueo = error_odt_bloqueada(odt)

            if bloqueo:
                messages.error(
                    request,
                    f"ODT {odt.numero}: {bloqueo}",
                )
                return redirect("bandeja")

        actualizadas = 0

        for odt in odts:

            revision = (
                Revision.objects
                .select_for_update()
                .filter(odt=odt)
                .first()
            )

            anterior = (
                revision.estado
                if revision
                else "APROBADA"
            )

            if anterior == "POR_REVISAR":
                anterior = "APROBADA"

            if anterior == nuevo:
                continue

            if revision is None:
                revision = Revision(odt=odt)

            revision.estado = nuevo
            revision.observacion = comentario
            revision.actualizado_por = request.user
            revision.save()

            EventoRevision.objects.create(
                odt=odt,
                estado_anterior=anterior,
                estado_nuevo=nuevo,
                comentario=(
                    f"Revisión: {anterior} → {nuevo}"
                    + (
                        f" | Motivo: {comentario}"
                        if comentario else ""
                    )
                ),
                usuario=request.user,
            )

            actualizadas += 1

    messages.success(
        request,
        f"{actualizadas} ODT actualizadas a {validos[nuevo]}.",
    )

    return redirect("bandeja")


@login_required
@permission_required("revisiones.editar_odt_sstt", raise_exception=True)
@require_POST
def guardar_fila(request):
    """
    Guarda cambios manuales sin modificar los datos
    originales importados desde SoftGuard.

    La revisión se modifica por su endpoint independiente.
    """

    try:
        numero = int(request.POST.get("numero", ""))
        if numero <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return JsonResponse(
            {"error": "Número de ODT inválido."},
            status=400,
        )

    servicio = request.POST.get("servicio", "").strip()
    monto_texto = request.POST.get("monto", "").strip()
    estado = request.POST.get("estado", "APROBADA").strip()
    comentario = request.POST.get("comentario", "").strip()

    estados_validos = (
        "APROBADA",
        "EN_REVISION",
        "RECHAZADA",
    )

    if estado not in estados_validos:
        return JsonResponse(
            {"error": "Estado de revisión inválido."},
            status=400,
        )

    if not servicio or len(servicio) > 150:
        return JsonResponse(
            {
                "error": (
                    "El servicio es obligatorio "
                    "y admite máximo 150 caracteres."
                )
            },
            status=400,
        )

    try:
        monto = Decimal(monto_texto)

        if (
            not monto.is_finite()
            or monto < 0
            or monto > Decimal("999999999999.99")
            or monto.as_tuple().exponent < -2
        ):
            raise InvalidOperation

    except (InvalidOperation, ValueError):
        return JsonResponse(
            {
                "error": (
                    "Monto inválido. Utiliza un valor "
                    "no negativo con máximo 2 decimales."
                )
            },
            status=400,
        )

    with transaction.atomic():
        odt = get_object_or_404(
            ODT.objects.select_for_update(),
            numero=numero,
        )

        bloqueo = error_odt_bloqueada(odt)

        if bloqueo:
            return JsonResponse(
                {"error": bloqueo},
                status=409,
            )

        # Valor efectivo antes de la modificación.
        monto_anterior = (
            odt.valor_pago_editado
            if odt.valor_pago_editado is not None
            else odt.valor_pago_tecnico
        )

        servicio_anterior = (
            odt.servicio_editado
            if odt.servicio_editado is not None
            else odt.servicio
        )

        cambio_monto = monto != monto_anterior
        cambio_servicio = servicio != servicio_anterior

        # Confirmación obligatoria en servidor.
        if (
            cambio_monto
            and request.POST.get("confirmar_monto") != "SI"
        ):
            return JsonResponse(
                {
                    "error": (
                        "Debes confirmar expresamente "
                        "el cambio de monto."
                    )
                },
                status=400,
            )

        revision_existente = (
            Revision.objects
            .select_for_update()
            .filter(odt=odt)
            .first()
        )

        estado_guardado = (
            revision_existente.estado
            if revision_existente
            else None
        )

        # Estado efectivo de la nueva lógica.
        estado_anterior = (
            "APROBADA"
            if estado_guardado in (
                None,
                "POR_REVISAR",
            )
            else estado_guardado
        )

        cambio_estado = False
        estado = estado_anterior

        if not (
            cambio_monto
            or cambio_servicio
            or cambio_estado
        ):
            return JsonResponse(
                {
                    "ok": True,
                    "mensaje": "No hay cambios para guardar.",
                    "monto": str(monto),
                    "estado": estado_anterior,
                }
            )

        # Guardar solo diferencias respecto de SoftGuard.
        odt.servicio_editado = (
            servicio
            if servicio != odt.servicio
            else None
        )

        odt.valor_pago_editado = (
            monto
            if monto != odt.valor_pago_tecnico
            else None
        )

        odt.modificado_manualmente = bool(
            odt.servicio_editado is not None
            or odt.valor_pago_editado is not None
        )

        odt.save(
            update_fields=[
                "servicio_editado",
                "valor_pago_editado",
                "modificado_manualmente",
            ]
        )

        registrar_cambio_manual(odt, request.user)

        # Solo crear/actualizar revisión cuando cambia
        # expresamente el estado.
        if cambio_estado:
            revision, _ = (
                Revision.objects
                .select_for_update()
                .get_or_create(odt=odt)
            )

            revision.estado = estado
            revision.observacion = comentario
            revision.actualizado_por = request.user
            revision.save()

        cambios = []

        if cambio_servicio:
            cambios.append(
                f"Servicio: {servicio_anterior} → {servicio}"
            )

        if cambio_monto:
            cambios.append(
                f"Pago técnico: ${monto_anterior} → ${monto}"
            )

        if cambio_estado:
            cambios.append(
                f"Revisión: {estado_anterior} → {estado}"
            )

        if comentario:
            cambios.append(f"Motivo: {comentario}")

        EventoRevision.objects.create(
            odt=odt,
            estado_anterior=estado_anterior,
            estado_nuevo=estado,
            comentario=" | ".join(cambios),
            usuario=request.user,
        )

    return JsonResponse(
        {
            "ok": True,
            "mensaje": "Cambios guardados correctamente.",
            "monto": str(monto),
            "estado": estado,
        }
    )







@login_required
@permission_required("revisiones.ver_historial_sstt", raise_exception=True)
def historial_odt(request, numero):
    """
    Historial operativo de la ODT obtenido
    directamente desde SoftGuard.
    """

    get_object_or_404(ODT, numero=numero)

    try:
        movimientos = consultar_historial_odt(numero)

        
        movimientos = sorted(
            movimientos,
            key=lambda movimiento: (
                movimiento.get("FechaHora") is not None,
                movimiento.get("FechaHora").isoformat()
                if movimiento.get("FechaHora") else "",
            ),
            reverse=True,
        )


        historial = []

        for movimiento in movimientos:
            fecha = movimiento.get("FechaHora")

            historial.append({
                "fecha": (
                    fecha.isoformat()
                    if fecha else None
                ),
                "accion": movimiento.get("Accion") or "",
                "observacion": (
                    movimiento.get("Observacion") or ""
                ),
                "id_usuario": movimiento.get("IDUsuario"),
                "usuario": (
                    movimiento.get("NombreUsuario")
                    or "Usuario no identificado"
                ),
                "correo_usuario": (
                    movimiento.get("CorreoUsuario") or ""
                ),
                "correo_observacion": (
                    movimiento.get("CorreoObservacion") or ""
                ),
            })

        return JsonResponse({
            "ok": True,
            "numero": numero,
            "total": len(historial),
            "eventos": historial,
        })

    except Exception:
        return JsonResponse({
            "ok": False,
            "error": (
                "No se pudo consultar el historial "
                "de SoftGuard. Verifica la conexión SQL."
            ),
        }, status=503)



@login_required
@permission_required("revisiones.revisar_pago_sstt", raise_exception=True)
@require_POST


@login_required
@permission_required(
    "revisiones.revisar_pago_sstt",
    raise_exception=True,
)
@require_POST
def actualizar_revision(request):

    
    # ==================================================
    # VALIDAR NÚMERO DE ODT
    # Acepta 77527, 77 527 y 77.527
    # ==================================================

    numero_texto = str(
        request.POST.get("numero", "")
    ).strip()

    # Conservar únicamente números.
    numero_limpio = "".join(
        caracter
        for caracter in numero_texto
        if caracter in "0123456789"
    )

    if not numero_limpio:
        return JsonResponse(
            {
                "error": (
                    "Número de ODT inválido. "
                    f"Valor recibido: {numero_texto!r}"
                )
            },
            status=400,
        )

    numero = int(numero_limpio)

    if numero <= 0:
        return JsonResponse(
            {"error": "Número de ODT inválido."},
            status=400,
        )


    estado = request.POST.get("estado", "").strip()
    comentario = request.POST.get("comentario", "").strip()

    validos = (
        "APROBADA",
        "EN_REVISION",
        "RECHAZADA",
    )

    if estado not in validos:
        return JsonResponse(
            {"error": "Estado de revisión inválido."},
            status=400,
        )

    if estado in ("EN_REVISION", "RECHAZADA") and not comentario:
        return JsonResponse(
            {
                "error": (
                    "Debes indicar el motivo para "
                    "cambiar a En revisión o Rechazada."
                )
            },
            status=400,
        )

    with transaction.atomic():

        odt = get_object_or_404(
            ODT.objects.select_for_update(),
            numero=numero,
        )

        bloqueo = error_odt_bloqueada(odt)

        if bloqueo:
            return JsonResponse(
                {"error": bloqueo},
                status=409,
            )

        revision = (
            Revision.objects
            .select_for_update()
            .filter(odt=odt)
            .first()
        )

        anterior = (
            revision.estado
            if revision
            else "APROBADA"
        )

        if anterior == "POR_REVISAR":
            anterior = "APROBADA"

        if anterior == estado:
            return JsonResponse({
                "ok": True,
                "mensaje": "El estado no ha cambiado.",
                "estado": estado,
            })

        if revision is None:
            revision = Revision(odt=odt)

        revision.estado = estado
        revision.observacion = comentario
        revision.actualizado_por = request.user
        revision.save()

        EventoRevision.objects.create(
            odt=odt,
            estado_anterior=anterior,
            estado_nuevo=estado,
            comentario=(
                f"Revisión: {anterior} → {estado}"
                + (
                    f" | Motivo: {comentario}"
                    if comentario else ""
                )
            ),
            usuario=request.user,
        )

    return JsonResponse({
        "ok": True,
        "mensaje": "Estado de revisión actualizado.",
        "estado": estado,
    })





@login_required
@permission_required(
    "revisiones.cambiar_informe_sstt",
    raise_exception=True,
)
@require_POST
def actualizar_informe(request):

    try:
        numero = int(request.POST.get("numero", ""))

        if numero <= 0:
            raise ValueError

    except (ValueError, TypeError):
        return JsonResponse(
            {"error": "Número de ODT inválido."},
            status=400,
        )

    estado = request.POST.get("estado", "").strip()
    validos = dict(ODT.ESTADOS_INFORME)

    if estado not in validos:
        return JsonResponse(
            {"error": "Estado de informe inválido."},
            status=400,
        )

    with transaction.atomic():

        odt = get_object_or_404(
            ODT.objects.select_for_update(),
            numero=numero,
        )

        # Bloquear ODT facturadas o rechazadas.
        bloqueo = error_odt_bloqueada(odt)

        if bloqueo:
            return JsonResponse(
                {"error": bloqueo},
                status=409,
            )

        anterior = odt.estado_informe

        if anterior == estado:
            return JsonResponse({
                "ok": True,
                "mensaje": "Sin cambios.",
                "estado": estado,
            })

        odt.estado_informe = estado
        odt.informe_actualizado_por = request.user
        odt.informe_actualizado_en = timezone.now()

        odt.save(
            update_fields=[
                "estado_informe",
                "informe_actualizado_por",
                "informe_actualizado_en",
            ]
        )

        estado_revision = (
            Revision.objects
            .filter(odt=odt)
            .values_list("estado", flat=True)
            .first()
        ) or "APROBADA"

        if estado_revision == "POR_REVISAR":
            estado_revision = "APROBADA"

        EventoRevision.objects.create(
            odt=odt,
            estado_anterior=estado_revision,
            estado_nuevo=estado_revision,
            comentario=(
                f"Informe: {validos.get(anterior, anterior)} "
                f"→ {validos[estado]}"
            ),
            usuario=request.user,
        )

    return JsonResponse({
        "ok": True,
        "mensaje": "Estado de informe actualizado.",
        "estado": estado,
    })



# ==========================================================
# ADMINISTRACIÓN DE CUENTAS SSTT
# ==========================================================

@login_required
@permission_required("revisiones.administrar_cuentas_sstt", raise_exception=True)
def administrar_cuentas(request):

    busqueda = request.GET.get("q", "").strip()
    tipo = request.GET.get("tipo", "").strip()
    pendientes = request.GET.get("pendientes", "").strip()

    cuentas = CatalogoCuenta.objects.all()

    if busqueda:
        cuentas = cuentas.filter(
            Q(codigo_cuenta__icontains=busqueda)
            | Q(nombre_cuenta__icontains=busqueda)
            | Q(ceco__icontains=busqueda)
        )

    if tipo in ("B2B", "B2C", "SIN_CLASIFICAR"):
        cuentas = cuentas.filter(tipo_cliente=tipo)

    if pendientes == "1":
        cuentas = cuentas.filter(
            Q(tipo_cliente="SIN_CLASIFICAR")
            | Q(requiere_revision_ceco=True)
            | Q(ceco="")
        )

    total_cuentas = CatalogoCuenta.objects.count()

    sin_clasificar = CatalogoCuenta.objects.filter(
        tipo_cliente="SIN_CLASIFICAR"
    ).count()

    revisar_ceco = CatalogoCuenta.objects.filter(
        requiere_revision_ceco=True
    ).count()

    pagina = Paginator(
        cuentas.order_by("codigo_cuenta"),
        50
    ).get_page(request.GET.get("page"))

    parametros = request.GET.copy()
    parametros.pop("page", None)

    return render(
        request,
        "revisiones/administrar_cuentas.html",
        {
            "pagina": pagina,
            "cuentas": pagina.object_list,
            "busqueda": busqueda,
            "tipo": tipo,
            "pendientes": pendientes,
            "total_cuentas": total_cuentas,
            "sin_clasificar": sin_clasificar,
            "revisar_ceco": revisar_ceco,
            "querystring": parametros.urlencode(),
        },
    )


@login_required
@permission_required("revisiones.administrar_cuentas_sstt", raise_exception=True)
@require_POST
def guardar_cuenta(request, cuenta_id):

    tipos_validos = {
        "B2B",
        "B2C",
        "SIN_CLASIFICAR",
    }

    tipo = request.POST.get("tipo_cliente", "").strip()
    ceco = request.POST.get("ceco", "").strip()
    observaciones = request.POST.get(
        "observaciones", ""
    ).strip()

    if tipo not in tipos_validos:
        messages.error(
            request,
            "La clasificación seleccionada no es válida."
        )
        return redirect("administrar_cuentas")

    if len(ceco) > 50:
        messages.error(
            request,
            "El CECO no puede superar 50 caracteres."
        )
        return redirect("administrar_cuentas")

    with transaction.atomic():

        cuenta = get_object_or_404(
            CatalogoCuenta.objects.select_for_update(),
            pk=cuenta_id,
        )

        cuenta.tipo_cliente = tipo
        cuenta.ceco = ceco
        cuenta.observaciones = observaciones
        cuenta.requiere_revision_ceco = not bool(ceco)
        cuenta.actualizado_por = request.user

        cuenta.save()

        # Sincronizar clasificación de las ODT de esta cuenta.
        # Se compara el código normalizado de SoftGuard.
        codigo_objetivo = cuenta.codigo_cuenta.strip().upper()

        odts_actualizar = []

        for odt in ODT.objects.only(
            "id",
            "cuenta_completa",
            "tipo_cliente",
        ).iterator(chunk_size=1000):

            codigo = normalizar_codigo_cuenta(
                odt.cuenta_completa
            )

            if (
                codigo == codigo_objetivo
                and odt.tipo_cliente != tipo
            ):
                odt.tipo_cliente = tipo
                odts_actualizar.append(odt)

        if odts_actualizar:
            ODT.objects.bulk_update(
                odts_actualizar,
                ["tipo_cliente"],
                batch_size=500,
            )

    messages.success(
        request,
        (
            f"Cuenta {cuenta.codigo_cuenta} actualizada. "
            f"{len(odts_actualizar)} ODT sincronizadas."
        ),
    )

    return redirect("administrar_cuentas")




@login_required
@permission_required(
    "revisiones.ver_bandeja_sstt",
    raise_exception=True
)
@login_required
@permission_required("revisiones.ver_bandeja_sstt", raise_exception=True)
def odt_modificadas(request):
    """Listado de cambios y comparación con la última sincronización SoftGuard."""
    from .coordinadores_softguard import (
        COORDINADORES_SOFTGUARD,
        identificar_coordinador_odt,
    )
    from django.db.models import F

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

    # Guardar resultados solo durante esta solicitud, para no repetir
    # la consulta SQL de historial por cada ODT.
    cache_coordinadores = {}

    def obtener_coordinador(numero):
        if numero not in cache_coordinadores:
            try:
                cache_coordinadores[numero] = identificar_coordinador_odt(numero)
            except Exception:
                cache_coordinadores[numero] = {
                    "nombre": "No disponible",
                    "usuario": None,
                    "identificado": False,
                }
        return cache_coordinadores[numero]

    # El coordinador no está guardado aún en ODT, por lo que el
    # filtro requiere identificarlo antes de calcular la paginación.
    if coordinador_seleccionado:
        numeros = registros.values_list("numero", flat=True).iterator()
        numeros_filtrados = []
        for numero in numeros:
            info = obtener_coordinador(numero)
            if coordinador_seleccionado == "SIN_IDENTIFICAR":
                coincide = not info.get("identificado", False)
            else:
                coincide = info.get("usuario") == coordinador_seleccionado
            if coincide:
                numeros_filtrados.append(numero)
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

    for odt in pagina.object_list:
        coordinador = obtener_coordinador(odt.numero)
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
        for datos in COORDINADORES_SOFTGUARD.values()
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


@login_required
@require_POST
def cambiar_estado_correccion(request):
    coordinador = es_coordinador_sstt(request.user)
    if not coordinador and not request.user.has_perm("revisiones.editar_odt_sstt"):
        raise PermissionDenied
    from .correcciones import coinciden
    try:
        numero_recibido = str(request.POST.get("numero", "")).strip()

        numero_limpio = "".join(
            caracter
            for caracter in numero_recibido
            if caracter.isdigit() and caracter.isascii()
        )

        if not numero_limpio:
            raise ValueError("Número de ODT vacío")

        numero = int(numero_limpio)

    except (TypeError, ValueError):
        return JsonResponse(
            {"error": "ODT inválida"},
            status=400
        )
    if coordinador:
        try:
            permitido = coordinador_visible(request, numero)
        except Exception:
            return JsonResponse({"error": "No se pudo verificar el coordinador en SQL."}, status=503)
        if not permitido:
            raise PermissionDenied
    estado = request.POST.get("estado", "").strip()
    if coordinador and estado != "EN_PROCESO":
        return JsonResponse({"error": "Solo puedes marcar la modificación como Procesada."}, status=400)
    if estado not in ("PENDIENTE", "EN_PROCESO"):
        return JsonResponse({"error": "Estado manual no permitido"}, status=400)
    with transaction.atomic():
        odt = get_object_or_404(ODT.objects.select_for_update(), numero=numero)
        seguimiento = CorreccionODT.objects.select_for_update().filter(odt=odt).first()
        if not seguimiento:
            if odt.servicio_editado is None and odt.valor_pago_editado is None:
                return JsonResponse({"error": "La ODT no tiene modificaciones."}, status=409)
            seguimiento = registrar_cambio_manual(odt, request.user)
        if seguimiento.estado == "ACTUALIZADA" or coinciden(odt, seguimiento):
            return JsonResponse({"error": "La ODT ya coincide con SoftGuard. Actualiza la pantalla."}, status=409)
        if seguimiento.estado != estado:
            anterior = seguimiento.estado
            seguimiento.estado = estado
            seguimiento.actualizado_por = request.user
            seguimiento.gestionado_en = timezone.now()
            seguimiento.save(update_fields=["estado", "actualizado_por", "gestionado_en"])
            EventoCorreccionODT.objects.create(odt=odt, estado_anterior=anterior,
                estado_nuevo=estado, usuario=request.user,
                detalle="Cambio manual del estado de gestión")
    return JsonResponse({"ok": True, "estado": estado})


@login_required
@require_POST
def asignar_coordinador(request):
    if not puede_asignar_coordinador(request.user):
        raise PermissionDenied("Solo admin y jiturriaga pueden asignar coordinadores.")
    try:
        numero = int(request.POST.get("numero", ""))
        if numero <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return JsonResponse({"error": "Número de ODT inválido."}, status=400)
    usuario = request.POST.get("coordinador", "").strip()
    datos = next((d for d in COORDINADORES_SOFTGUARD.values() if d["usuario"] == usuario), None)
    if datos is None:
        return JsonResponse({"error": "Coordinador inválido."}, status=400)
    with transaction.atomic():
        odt = get_object_or_404(ODT.objects.select_for_update(), numero=numero)
        if AsignacionCoordinadorODT.objects.filter(odt=odt).exists():
            return JsonResponse({"error": "La ODT ya tiene un coordinador asignado."}, status=409)
        try:
            info = identificar_coordinador_softguard(numero)
        except Exception:
            return JsonResponse({"error": "No se pudo verificar el coordinador en SoftGuard."}, status=503)
        if info.get("identificado", False):
            return JsonResponse({"error": "La ODT ya tiene coordinador identificado. Actualiza la pantalla."}, status=409)
        AsignacionCoordinadorODT.objects.create(
            odt=odt, usuario_coordinador=usuario, asignado_por=request.user)
        revision = Revision.objects.filter(odt=odt).first()
        estado = revision.estado if revision else "POR_REVISAR"
        EventoRevision.objects.create(
            odt=odt, estado_anterior=estado, estado_nuevo=estado,
            usuario=request.user, comentario=f"Coordinador asignado en SSTT: {datos['nombre']}")
    return JsonResponse({"ok": True, "coordinador": datos["nombre"]})
