"""Análisis operativo sobre la base local sincronizada."""
from datetime import date, datetime, time, timedelta
from collections import Counter
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET
from .models import ODT
from .metricas_analisis import cargar_metricas
from .dominio.servicios import SERVICIOS_PRINCIPALES
from .dominio.ranking_cuentas import ranking_cuentas


@login_required
@permission_required("revisiones.ver_bandeja_sstt", raise_exception=True)
@permission_required("revisiones.revisar_pago_sstt", raise_exception=True)
@require_GET
def analisis_odt(request):
    hoy = timezone.localdate()
    desde = request.GET.get("desde", hoy.replace(day=1).isoformat())
    hasta = request.GET.get("hasta", hoy.isoformat())
    campo = "finalizacion"
    errores = []
    qs = ODT.objects.filter(estado_softguard__iexact="Finalizado",fecha_finalizacion__isnull=False)
    for valor, operador in ((desde,"gte"),(hasta,"lt")):
        if valor:
            try:
                fecha=date.fromisoformat(valor)
                if operador=="lt":
                    fecha+=timedelta(days=1)
                limite=timezone.make_aware(datetime.combine(fecha,time.min))
                qs=qs.filter(**{f"fecha_finalizacion__{operador}":limite})
            except (ValueError,OverflowError):
                errores.append("Ingresa fechas válidas.")
    if desde and hasta and desde>hasta:
        errores.append("Desde no puede ser posterior a Hasta.")
    if errores:
        qs=qs.none()
    estado="Finalizado"
    q=request.GET.get("q","").strip()
    if q:
        qs=qs.filter(Q(cuenta_completa__icontains=q)|Q(tecnico__icontains=q)|Q(contratista__icontains=q))
    filas=cargar_metricas(qs)
    servicios_disponibles = sorted(set(SERVICIOS_PRINCIPALES) | {o.servicio_efectivo for o in filas if o.servicio_efectivo})
    servicios_seleccionados = (request.GET.getlist("servicios") if "servicios_filtrados" in request.GET or "servicios" in request.GET
                              else list(SERVICIOS_PRINCIPALES))
    filas = [o for o in filas if o.servicio_efectivo in servicios_seleccionados]
    cuenta=request.GET.get("cuenta", "").strip()
    if cuenta:
        filas = [o for o in filas if o.clave_cuenta_analisis == cuenta]
    servicio=request.GET.get("servicio","")
    sla=request.GET.get("sla","")
    preventivo=request.GET.get("preventivo","")
    recurrencia=request.GET.get("recurrencia","")
    incidencias_cuenta=request.GET.get("incidencias_cuenta","")
    if servicio:
        filas=[o for o in filas if (o.servicio_efectivo==servicio if servicio!="__SIN_SERVICIO__" else not o.servicio_efectivo)]
    if sla in ("CUMPLE","NO_CUMPLE","REVISAR"):
        filas=[o for o in filas if (o.estado_sla in ("SIN_DATOS","ERROR_FECHAS") if sla=="REVISAR" else o.estado_sla==sla)]
    if preventivo in ("con","sin"):
        filas=[o for o in filas if (o.fecha_ultimo_preventivo is not None)==(preventivo=="con")]
    if recurrencia in ("con","sin"):
        filas=[o for o in filas if (o.cantidad_incidencias>=2)==(recurrencia=="con")]

    if incidencias_cuenta in ("2","3","4mas"):
        filas=[o for o in filas if (o.incidencias_cuenta_90>=4 if incidencias_cuenta=="4mas" else o.incidencias_cuenta_90==int(incidencias_cuenta))]

    def enlace(clave=None, valor=None, **cambios):
        parametros = request.GET.copy()
        parametros.pop("page",None)
        parametros.pop("estado",None)
        parametros.pop("campo",None)
        if clave:
            parametros[clave] = "" if parametros.get(clave)==str(valor) else valor
        for k,v in cambios.items():
            parametros[k]=v
        return "?" + parametros.urlencode() + "#dashboard"

    ranking = ranking_cuentas(filas)
    for fila in ranking:
        fila["url"] = enlace("cuenta", fila["cuenta"])
        fila["activo"] = cuenta == fila["cuenta"]

    resumen={
        "total":len(filas),
        "cumple":sum(o.estado_sla=="CUMPLE" for o in filas),
        "no_cumple":sum(o.estado_sla=="NO_CUMPLE" for o in filas),
        "pendiente":0,
        "revisar_fechas":sum(o.estado_sla in ("SIN_DATOS","ERROR_FECHAS") for o in filas),
        "recurrentes":sum(o.cantidad_incidencias>=2 for o in filas),
        "con_preventivo":sum(o.fecha_ultimo_preventivo is not None for o in filas),
        "sin_preventivo":sum(o.fecha_ultimo_preventivo is None for o in filas),
    }
    evaluables=resumen["cumple"]+resumen["no_cumple"]
    resumen["porcentaje_sla"]=round(resumen["cumple"]*100/evaluables,1) if evaluables else None
    por_estado=[]
    por_servicio=[{"servicio_efectivo":nombre,"cantidad":cantidad}
                  for nombre,cantidad in Counter(o.servicio_efectivo for o in filas).most_common()]
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
    colores = ("#0d9488","#ee765c")
    sla_grafico = []
    segmentos, acumulado = [], 0
    for (nombre,clave,cantidad),color in zip((
        ("Cumple","CUMPLE",resumen["cumple"]),("No cumple","NO_CUMPLE",resumen["no_cumple"]),
    ),colores):
        fin = acumulado + (cantidad*100/evaluables if evaluables else 0)
        segmentos.append(f"{color} {acumulado:.3f}% {fin:.3f}%")
        sla_grafico.append({"nombre":nombre,"cantidad":cantidad,"porcentaje":round(cantidad*100/evaluables,1) if evaluables else None,"color":color,"url":enlace("sla",clave),"activo":sla==clave})
        acumulado=fin
    preventivos_grafico = [
        {"nombre":"Con preventivo","cantidad":resumen["con_preventivo"],"url":enlace("preventivo","con")},
        {"nombre":"Sin preventivo","cantidad":resumen["sin_preventivo"],"url":enlace("preventivo","sin")},
    ]
    recurrencias_grafico = [
        {"nombre":"Con atenciones repetidas","cantidad":resumen["recurrentes"],"url":enlace("recurrencia","con")},
        {"nombre":"Sin atenciones repetidas","cantidad":resumen["total"]-resumen["recurrentes"],"url":enlace("recurrencia","sin")},
    ]
    for grupo in (preventivos_grafico,recurrencias_grafico):
        for fila in grupo:
            fila["ancho"]=f'{fila["cantidad"]*100/resumen["total"]:.2f}' if resumen["total"] else "0"
    mensual = not desde or not hasta or (not errores and (date.fromisoformat(hasta)-date.fromisoformat(desde)).days>90)
    conteo_fechas=Counter()
    for o in filas:
        dia=timezone.localtime(o.fecha_finalizacion).date()
        conteo_fechas[dia.replace(day=1) if mensual else dia]+=1
    tendencia=[{"fecha_grafico":dia,"cantidad":cantidad} for dia,cantidad in sorted(conteo_fechas.items())]
    maximo=max((f["cantidad"] for f in tendencia),default=1) or 1
    for fila in tendencia:
        dia = fila["fecha_grafico"]
        if isinstance(dia, datetime):
            dia=timezone.localtime(dia).date()
        fin = ((dia.replace(day=28)+timedelta(days=4)).replace(day=1)-timedelta(days=1)) if mensual else dia
        fila["alto"]=f'{fila["cantidad"]*100/maximo:.2f}'
        fila["etiqueta"]=dia.strftime("%m/%Y" if mensual else "%d/%m")
        fila["url"]=enlace(desde=dia.isoformat(),hasta=fin.isoformat())
    cuentas_unicas = {o.clave_cuenta_analisis:o.incidencias_cuenta_90 for o in filas if o.clave_cuenta_analisis}
    incidencias_grafico = []
    for clave,nombre in (("2","2 incidencias"),("3","3 incidencias"),("4mas","4 o más incidencias")):
        cantidad=sum((v>=4 if clave=="4mas" else v==int(clave)) for v in cuentas_unicas.values())
        incidencias_grafico.append({"nombre":nombre,"cantidad":cantidad,"url":enlace("incidencias_cuenta",clave),"activo":incidencias_cuenta==clave})
    max_cuentas=max((g["cantidad"] for g in incidencias_grafico),default=0) or 1
    for g in incidencias_grafico:
        g["ancho"]=f'{g["cantidad"]*100/max_cuentas:.2f}'

    tarjetas = [
        {"nombre":"ODT analizadas","valor":resumen["total"],"url":enlace(estado="",servicio="",sla="",preventivo="",recurrencia="",incidencias_cuenta="",cuenta=""),"nota":"Quitar selecciones de gráficos","color":"azul"},
        {"nombre":"Cumplimiento SLA","valor":str(resumen["porcentaje_sla"])+" %" if evaluables else "—","url":enlace("sla","CUMPLE"),"nota":f"{evaluables} ODT evaluables","color":"verde"},
        {"nombre":"ODT con atenciones repetidas","valor":resumen["recurrentes"],"url":enlace("recurrencia","con"),"nota":"2 o más finalizadas · misma cuenta y contratista · últimos 90 días","color":"naranja"},
        {"nombre":"Sin preventivo registrado","valor":resumen["sin_preventivo"],"url":enlace("preventivo","sin"),"nota":"Antecedentes disponibles por cuenta","color":"violeta"},
    ]
    filtros_activos=[]
    for clave,titulo in (("cuenta","Cuenta"),("servicio","Servicio"),("sla","SLA"),("preventivo","Preventivo"),("recurrencia","Recurrencia"),("incidencias_cuenta","Incidencias por cuenta")):
        valor=request.GET.get(clave)
        if valor:
            etiquetas = {"CUMPLE":"Cumple","NO_CUMPLE":"No cumple","PENDIENTE":"Pendiente","REVISAR":"Revisar fechas",
                         "__SIN_ESTADO__":"Sin estado","__SIN_SERVICIO__":"Sin servicio","con":"Con registro","sin":"Sin registro","2":"2 incidencias","3":"3 incidencias","4mas":"4 o más incidencias"}
            filtros_activos.append({"nombre":f"{titulo}: {etiquetas.get(valor,valor)}","url":enlace(**{clave:""})})

    vista = request.GET.get("vista","todas")
    if vista=="incidencias":
        filas=[o for o in filas if o.cantidad_incidencias>=2]
    elif vista=="sla":
        filas=[o for o in filas if o.estado_sla=="NO_CUMPLE"]
    elif vista=="sin_preventivo":
        filas=[o for o in filas if o.fecha_ultimo_preventivo is None]
    elif vista!="todas":
        vista="todas"
    filas.sort(key=lambda o:(o.fecha_finalizacion,o.numero),reverse=True)
    pagina=Paginator(filas,50).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page",None)
    return render(request,"revisiones/analisis_odt.html",{
        "cuenta":cuenta, "ranking_cuentas":ranking,
        "incidencias_cuenta":incidencias_cuenta,"incidencias_grafico":incidencias_grafico,
        "cuentas_repetidas":sum(g["cantidad"] for g in incidencias_grafico),
        "url_revisar_fechas":enlace("sla","REVISAR"),
        "tarjetas":tarjetas,"sla_grafico":sla_grafico,
        "donut_fondo":"conic-gradient("+", ".join(segmentos)+")" if evaluables else "#e6edf5",
        "preventivos_grafico":preventivos_grafico,"recurrencias_grafico":recurrencias_grafico,
        "tendencia":tendencia,"tendencia_mensual":mensual,"filtros_activos":filtros_activos,
        "servicios_disponibles":servicios_disponibles,"servicios_seleccionados":servicios_seleccionados,
        "servicio":servicio,"sla":sla,"preventivo":preventivo,"recurrencia":recurrencia,
        "quitar_selecciones":enlace(estado="",servicio="",sla="",preventivo="",recurrencia="",incidencias_cuenta="",cuenta=""),
        "resumen":resumen,"por_estado":por_estado,"por_servicio":por_servicio,"pagina":pagina,
        "desde":desde,"hasta":hasta,"campo":campo,"estado":estado,"q":q,"vista":vista,
        "errores":errores,"querystring":params.urlencode(),
        "estados":[],
    })
