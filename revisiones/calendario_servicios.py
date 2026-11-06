"""Calendario de visitas reales de las ODT sincronizadas."""
import calendar
from datetime import date
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q
from django.db.models.functions import Coalesce, Lower, Trim
from django.shortcuts import render
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET
from .models import ODT
from .cuentas_utils import cargar_catalogo_cuentas, normalizar_codigo_cuenta
from .dominio.fechas import sumar_meses


@login_required
@permission_required("revisiones.ver_bandeja_sstt", raise_exception=True)
@require_GET
def calendario_servicios(request):
    hoy = timezone.localdate()
    errores = []
    try:
        mes = date.fromisoformat((request.GET.get("mes") or hoy.strftime("%Y-%m")) + "-01")
        if mes.year < 1900 or mes.year > 9998:
            raise ValueError
    except ValueError:
        mes = hoy.replace(day=1)
        errores.append("El mes no es válido.")
    ultimo = mes.replace(day=calendar.monthrange(mes.year, mes.month)[1])
    q = request.GET.get("q", "").strip()
    servicio = request.GET.get("servicio", "").strip()
    base = ODT.objects.annotate(
        estado_normalizado=Lower(Trim("estado_softguard")),
        servicio_efectivo=Coalesce("servicio_editado", "servicio"),
    ).filter(estado_normalizado__in=("asignado","pendiente","en proceso","finalizado"), fecha_visita__isnull=False)
    periodo = base.filter(fecha_visita__range=(mes, ultimo))
    valores = list(periodo.order_by("servicio_efectivo").values_list("servicio_efectivo",flat=True).distinct())
    servicios = sorted({v or "__SIN_SERVICIO__" for v in valores})
    if request.GET.get("formato") == "servicios":
        return JsonResponse({"servicios":servicios})
    explicita = "servicios_filtrados" in request.GET or "servicios" in request.GET
    if explicita:
        seleccion = request.GET.getlist("servicios")
    elif servicio:
        seleccion = [servicio]  # Compatibilidad con enlaces anteriores.
    else:
        seleccion = list(servicios)
    seleccionados = [s for s in seleccion if s in servicios]
    odts = periodo
    if q:
        odts = odts.filter(Q(cuenta_completa__icontains=q) | Q(tecnico__icontains=q) | Q(contratista__icontains=q))
    if seleccionados:
        condicion = Q(servicio_efectivo__in=[s for s in seleccionados if s!="__SIN_SERVICIO__"])
        if "__SIN_SERVICIO__" in seleccionados:
            condicion |= Q(servicio_efectivo="") | Q(servicio_efectivo__isnull=True)
        odts=odts.filter(condicion)
    else:
        odts=odts.none()
    odts = list(odts.order_by("fecha_visita", "cuenta_completa", "numero"))
    catalogo = cargar_catalogo_cuentas(o.cuenta_completa for o in odts)
    eventos = {}
    totales = {"realizadas":0,"abiertas":0,"atrasadas":0}
    for odt in odts:
        codigo = normalizar_codigo_cuenta(odt.cuenta_completa)
        cuenta = catalogo.get(codigo)
        if odt.estado_normalizado == "finalizado":
            categoria, etiqueta = "realizadas", "Realizada"
        elif odt.fecha_visita < hoy:
            categoria, etiqueta = "atrasadas", "Atrasada"
        else:
            categoria, etiqueta = "abiertas", "Abierta"
        totales[categoria] += 1
        eventos.setdefault(odt.fecha_visita, []).append({
            "categoria":categoria,"etiqueta":etiqueta,"estado":odt.estado_softguard.strip(),
            "codigo": codigo or "Sin código de cuenta",
            "nombre": cuenta.nombre_cuenta if cuenta and cuenta.nombre_cuenta else odt.cuenta_completa or "Sin cuenta",
            "numero": odt.numero, "servicio": odt.servicio_efectivo,
            "tecnico": odt.tecnico or odt.contratista or "Sin técnico",
        })
    semanas = [[{"fecha": dia, "del_mes": dia.month == mes.month, "hoy": dia == hoy,
                 "eventos": eventos.get(dia, [])}
                for dia in semana]
               for semana in calendar.Calendar(firstweekday=0).monthdatescalendar(mes.year, mes.month)]
    parametros = request.GET.copy()
    parametros.pop("formato",None)
    parametros.pop("servicio",None)
    if set(seleccionados) == set(servicios) and not (explicita and not seleccion):
        parametros.pop("servicios",None)
        parametros.pop("servicios_filtrados",None)
    else:
        parametros["servicios_filtrados"]="1"
        parametros.setlist("servicios",seleccion)

    parametros["mes"] = sumar_meses(mes, -1).strftime("%Y-%m")
    anterior = "?" + parametros.urlencode()
    parametros["mes"] = sumar_meses(mes, 1).strftime("%Y-%m")
    return render(request, "revisiones/calendario_servicios.html", {
        "totales":totales,
        "mes": mes.strftime("%Y-%m"), "mes_titulo": mes, "semanas": semanas, "errores": errores,
        "q": q, "servicio": servicio, "servicios": servicios, "servicios_seleccionados":seleccionados, "cantidad": len(odts),
        "cuentas": len({normalizar_codigo_cuenta(o.cuenta_completa) or o.cuenta_completa for o in odts}),
        "url_mes_anterior": anterior, "url_mes_siguiente": "?" + parametros.urlencode(),
    })
