"""Análisis operativo sobre la base local sincronizada."""
from datetime import date
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.db.models.functions import Coalesce
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
        qs = qs.filter(estado_softguard=estado)
    if q:
        qs = qs.filter(Q(cuenta_completa__icontains=q)|Q(tecnico__icontains=q)|Q(contratista__icontains=q))
    qs = con_indicadores_odt(qs)
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
    por_servicio = list(qs.annotate(servicio_efectivo=Coalesce("servicio_editado","servicio"))
                        .order_by().values("servicio_efectivo").annotate(cantidad=Count("pk")).order_by("-cantidad"))
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
        "resumen":resumen,"por_estado":por_estado,"por_servicio":por_servicio,"pagina":pagina,
        "desde":desde,"hasta":hasta,"campo":campo,"estado":estado,"q":q,"vista":vista,
        "errores":errores,"querystring":params.urlencode(),
        "estados":ODT.objects.exclude(estado_softguard="").order_by("estado_softguard").values_list("estado_softguard",flat=True).distinct(),
    })
