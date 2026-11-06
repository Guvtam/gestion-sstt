"""Análisis operativo sobre la base local sincronizada."""
from datetime import date, datetime, timedelta
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.db.models.functions import Coalesce, TruncDate, TruncMonth
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET
from .models import ODT
from .indicadores_odt import con_indicadores_odt


@login_required
@permission_required("revisiones.ver_bandeja_sstt", raise_exception=True)
@permission_required("revisiones.revisar_pago_sstt", raise_exception=True)
@require_GET
def analisis_odt(request):
    hoy = timezone.localdate()
    desde = request.GET.get("desde", hoy.replace(day=1).isoformat())
    hasta = request.GET.get("hasta", hoy.isoformat())
    campo = request.GET.get("campo", "creacion")
    if campo not in ("creacion", "finalizacion"):
        campo = "creacion"
    errores = []
    qs = ODT.objects.all()
    for valor, operador in ((desde, "gte"), (hasta, "lte")):
        if valor:
            try:
                fecha = date.fromisoformat(valor)
                qs = qs.filter(**{f"fecha_{campo}__date__{operador}":fecha})
            except ValueError:
                errores.append("Ingresa fechas válidas.")
    if desde and hasta and desde > hasta:
        errores.append("Desde no puede ser posterior a Hasta.")
    if errores:
        qs = qs.none()
    estado = request.GET.get("estado", "").strip()
    q = request.GET.get("q", "").strip()
    if estado:
        qs = qs.filter(estado_softguard=estado) if estado != "__SIN_ESTADO__" else qs.filter(estado_softguard="")
    if q:
        qs = qs.filter(Q(cuenta_completa__icontains=q)|Q(tecnico__icontains=q)|Q(contratista__icontains=q))
    qs = con_indicadores_odt(qs).annotate(servicio_efectivo=Coalesce("servicio_editado","servicio"))
    servicio = request.GET.get("servicio","")
    sla = request.GET.get("sla","")
    preventivo = request.GET.get("preventivo","")
    recurrencia = request.GET.get("recurrencia","")
    if servicio:
        qs = qs.filter(servicio_efectivo=servicio) if servicio != "__SIN_SERVICIO__" else qs.filter(Q(servicio_efectivo="")|Q(servicio_efectivo__isnull=True))
    opciones_sla = {
        "CUMPLE":Q(estado_sla="CUMPLE"), "NO_CUMPLE":Q(estado_sla="NO_CUMPLE"),
        "PENDIENTE":Q(estado_sla="PENDIENTE"), "REVISAR":Q(estado_sla__in=["SIN_DATOS","ERROR_FECHAS"]),
    }
    if sla in opciones_sla:
        qs = qs.filter(opciones_sla[sla])
    if preventivo in ("con","sin"):
        qs = qs.filter(fecha_ultimo_preventivo__isnull=(preventivo=="sin"))
    if recurrencia in ("con","sin"):
        qs = qs.filter(Q(cantidad_incidencias__gte=2) if recurrencia=="con" else Q(cantidad_incidencias__lt=2))

    def enlace(clave=None, valor=None, **cambios):
        parametros = request.GET.copy()
        parametros.pop("page",None)
        if clave:
            parametros[clave] = "" if parametros.get(clave)==str(valor) else valor
        for k,v in cambios.items():
            parametros[k]=v
        return "?" + parametros.urlencode() + "#dashboard"

    resumen = qs.aggregate(
        total=Count("pk"),
        cumple=Count("pk",filter=Q(estado_sla="CUMPLE")),
        no_cumple=Count("pk",filter=Q(estado_sla="NO_CUMPLE")),
        pendiente=Count("pk",filter=Q(estado_sla="PENDIENTE")),
        revisar_fechas=Count("pk",filter=Q(estado_sla__in=["SIN_DATOS","ERROR_FECHAS"])),
        recurrentes=Count("pk",filter=Q(cantidad_incidencias__gte=2)),
        con_preventivo=Count("pk",filter=Q(fecha_ultimo_preventivo__isnull=False)),
        sin_preventivo=Count("pk",filter=Q(fecha_ultimo_preventivo__isnull=True)),
    )
    evaluables = resumen["cumple"] + resumen["no_cumple"]
    resumen["porcentaje_sla"] = round(resumen["cumple"]*100/evaluables,1) if evaluables else None
    por_estado = list(qs.order_by().values("estado_softguard").annotate(cantidad=Count("pk")).order_by("-cantidad"))
    por_servicio = list(qs
                        .order_by().values("servicio_efectivo").annotate(cantidad=Count("pk")).order_by("-cantidad"))
    def barras(filas, campo_nombre, clave_filtro):
        maximo = max((f["cantidad"] for f in filas),default=1) or 1
        for fila in filas:
            nombre = fila[campo_nombre]
            valor = nombre or ("__SIN_ESTADO__" if clave_filtro=="estado" else "__SIN_SERVICIO__")
            fila["nombre"] = nombre or "Sin información"
            fila["ancho"] = f'{fila["cantidad"]*100/maximo:.2f}'
            fila["url"] = enlace(clave_filtro,valor)
            fila["activo"] = request.GET.get(clave_filtro)==valor
        return filas
    barras(por_estado,"estado_softguard","estado")
    barras(por_servicio,"servicio_efectivo","servicio")
    colores = ("#0d9488","#ee765c","#4c82cf","#a3afc0")
    sla_grafico = []
    segmentos, acumulado = [], 0
    for (nombre,clave,cantidad),color in zip((
        ("Cumple","CUMPLE",resumen["cumple"]),("No cumple","NO_CUMPLE",resumen["no_cumple"]),
        ("Pendiente","PENDIENTE",resumen["pendiente"]),("Revisar fechas","REVISAR",resumen["revisar_fechas"]),
    ),colores):
        fin = acumulado + (cantidad*100/resumen["total"] if resumen["total"] else 0)
        segmentos.append(f"{color} {acumulado:.3f}% {fin:.3f}%")
        sla_grafico.append({"nombre":nombre,"cantidad":cantidad,"color":color,"url":enlace("sla",clave),"activo":sla==clave})
        acumulado=fin
    preventivos_grafico = [
        {"nombre":"Con preventivo","cantidad":resumen["con_preventivo"],"url":enlace("preventivo","con")},
        {"nombre":"Sin preventivo","cantidad":resumen["sin_preventivo"],"url":enlace("preventivo","sin")},
    ]
    recurrencias_grafico = [
        {"nombre":"Con recurrencia","cantidad":resumen["recurrentes"],"url":enlace("recurrencia","con")},
        {"nombre":"Sin recurrencia","cantidad":resumen["total"]-resumen["recurrentes"],"url":enlace("recurrencia","sin")},
    ]
    for filas in (preventivos_grafico,recurrencias_grafico):
        for fila in filas:
            fila["ancho"]=f'{fila["cantidad"]*100/resumen["total"]:.2f}' if resumen["total"] else "0"
    mensual = not desde or not hasta or (not errores and (date.fromisoformat(hasta)-date.fromisoformat(desde)).days>90)
    agrupacion = TruncMonth(f"fecha_{campo}") if mensual else TruncDate(f"fecha_{campo}")
    tendencia=list(qs.order_by().annotate(fecha_grafico=agrupacion).exclude(fecha_grafico__isnull=True)
                   .values("fecha_grafico").annotate(cantidad=Count("pk")).order_by("fecha_grafico"))
    maximo=max((f["cantidad"] for f in tendencia),default=1) or 1
    for fila in tendencia:
        dia = fila["fecha_grafico"]
        if isinstance(dia, datetime):
            dia=timezone.localtime(dia).date()
        fin = ((dia.replace(day=28)+timedelta(days=4)).replace(day=1)-timedelta(days=1)) if mensual else dia
        fila["alto"]=f'{fila["cantidad"]*100/maximo:.2f}'
        fila["etiqueta"]=dia.strftime("%m/%Y" if mensual else "%d/%m")
        fila["url"]=enlace(desde=dia.isoformat(),hasta=fin.isoformat())
    tarjetas = [
        {"nombre":"ODT analizadas","valor":resumen["total"],"url":enlace(estado="",servicio="",sla="",preventivo="",recurrencia=""),"nota":"Quitar selecciones de gráficos","color":"azul"},
        {"nombre":"Cumplimiento SLA","valor":str(resumen["porcentaje_sla"])+" %" if evaluables else "—","url":enlace("sla","CUMPLE"),"nota":f"{evaluables} ODT evaluables","color":"verde"},
        {"nombre":"ODT con recurrencia","valor":resumen["recurrentes"],"url":enlace("recurrencia","con"),"nota":"Misma cuenta y contratista · 90 días","color":"naranja"},
        {"nombre":"Sin preventivo registrado","valor":resumen["sin_preventivo"],"url":enlace("preventivo","sin"),"nota":"Antecedentes disponibles por cuenta","color":"violeta"},
    ]
    filtros_activos=[]
    for clave,titulo in (("estado","Estado"),("servicio","Servicio"),("sla","SLA"),("preventivo","Preventivo"),("recurrencia","Recurrencia")):
        valor=request.GET.get(clave)
        if valor:
            etiquetas = {"CUMPLE":"Cumple","NO_CUMPLE":"No cumple","PENDIENTE":"Pendiente","REVISAR":"Revisar fechas",
                         "__SIN_ESTADO__":"Sin estado","__SIN_SERVICIO__":"Sin servicio","con":"Con registro","sin":"Sin registro"}
            filtros_activos.append({"nombre":f"{titulo}: {etiquetas.get(valor,valor)}","url":enlace(**{clave:""})})

    vista = request.GET.get("vista","todas")
    condiciones = {
        "incidencias": Q(cantidad_incidencias__gte=2),
        "sla": Q(estado_sla="NO_CUMPLE"),
        "sin_preventivo":Q(fecha_ultimo_preventivo__isnull=True),
    }
    if vista in condiciones:
        qs = qs.filter(condiciones[vista])
    elif vista != "todas":
        vista = "todas"
    pagina = Paginator(qs.order_by("-fecha_creacion","-numero"),50).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page",None)
    return render(request,"revisiones/analisis_odt.html",{
        "tarjetas":tarjetas,"sla_grafico":sla_grafico,
        "donut_fondo":"conic-gradient("+", ".join(segmentos)+")" if resumen["total"] else "#e6edf5",
        "preventivos_grafico":preventivos_grafico,"recurrencias_grafico":recurrencias_grafico,
        "tendencia":tendencia,"tendencia_mensual":mensual,"filtros_activos":filtros_activos,
        "servicio":servicio,"sla":sla,"preventivo":preventivo,"recurrencia":recurrencia,
        "quitar_selecciones":enlace(estado="",servicio="",sla="",preventivo="",recurrencia=""),
        "resumen":resumen,"por_estado":por_estado,"por_servicio":por_servicio,"pagina":pagina,
        "desde":desde,"hasta":hasta,"campo":campo,"estado":estado,"q":q,"vista":vista,
        "errores":errores,"querystring":params.urlencode(),
        "estados":ODT.objects.exclude(estado_softguard="").order_by("estado_softguard").values_list("estado_softguard",flat=True).distinct(),
    })
