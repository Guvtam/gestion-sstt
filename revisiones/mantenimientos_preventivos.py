"""Consulta de preventivos desde la última sincronización local de ODT."""
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db.models.functions import Coalesce
from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET
from .models import ODT, CatalogoCuenta
from .cuentas_utils import normalizar_codigo_cuenta, normalizar_tipo_cliente


SERVICIOS_PREVENTIVOS = ("MANTENIMIENTO PREVENTIVO", "MANTENCION PREVENTIVA", "PREVENTIVO")


@login_required
@permission_required("revisiones.ver_bandeja_sstt", raise_exception=True)
@require_GET
def mantenimientos_preventivos(request):
    q = request.GET.get("q", "").strip()
    filtro = request.GET.get("situacion", "").strip()
    cuenta_seleccionada = request.GET.get("cuenta", "").strip().upper()
    cuentas = {}
    for cuenta in CatalogoCuenta.objects.all().iterator(chunk_size=1000):
        codigo = normalizar_codigo_cuenta(cuenta.codigo_cuenta)
        if not codigo:
            continue
        cuentas[codigo] = {
            "codigo": codigo, "nombre": cuenta.nombre_cuenta,
            "tipo_cliente": normalizar_tipo_cliente(cuenta.tipo_cliente), "ceco": cuenta.ceco,
            "cantidad": 0, "pendientes": 0, "ultimo": None,
        }
    # Incorporar cuentas que aún no estén registradas en el catálogo.
    for texto in ODT.objects.order_by().values_list("cuenta_completa", flat=True).distinct().iterator(chunk_size=1000):
        codigo = normalizar_codigo_cuenta(texto)
        if codigo in cuentas and not cuentas[codigo]["nombre"]:
            cuentas[codigo]["nombre"] = texto
        if codigo and codigo not in cuentas:
            cuentas[codigo] = {"codigo": codigo, "nombre": texto, "tipo_cliente": "SIN_CLASIFICAR",
                              "ceco": "", "cantidad": 0, "pendientes": 0, "ultimo": None}

    condiciones = Q()
    for servicio in SERVICIOS_PREVENTIVOS:
        condiciones |= Q(servicio_efectivo__iexact=servicio)
    preventivos = (ODT.objects.annotate(servicio_efectivo=Coalesce("servicio_editado", "servicio"))
                   .filter(condiciones).order_by("-fecha_finalizacion", "-numero"))
    detalle = []
    for odt in preventivos.iterator(chunk_size=1000):
        codigo = normalizar_codigo_cuenta(odt.cuenta_completa)
        if codigo not in cuentas:
            continue
        cuenta = cuentas[codigo]
        cuenta["cantidad"] += 1
        finalizado = odt.estado_softguard.strip().casefold() == "finalizado"
        if not finalizado and odt.estado_softguard.strip().casefold() != "cancelado":
            cuenta["pendientes"] += 1
        # Solo una ODT finalizada con fecha acredita un mantenimiento realizado.
        if finalizado and odt.fecha_finalizacion is not None:
            actual = cuenta["ultimo"]
            if actual is None or (odt.fecha_finalizacion, odt.numero) > (actual.fecha_finalizacion, actual.numero):
                cuenta["ultimo"] = odt
        if codigo == cuenta_seleccionada:
            detalle.append(odt)

    filas = []
    for cuenta in cuentas.values():
        ultimo = cuenta["ultimo"]
        cuenta["dias"] = (
            (timezone.localdate() - timezone.localtime(ultimo.fecha_finalizacion).date()).days
            if ultimo else None
        )
        if q and q.casefold() not in (" ".join((cuenta["codigo"], cuenta["nombre"], cuenta["ceco"]))).casefold():
            continue
        if filtro == "SIN_PREVENTIVO" and ultimo is not None:
            continue
        if filtro == "CON_PREVENTIVO" and ultimo is None:
            continue
        if filtro == "PENDIENTES" and not cuenta["pendientes"]:
            continue
        filas.append(cuenta)
    filas.sort(key=lambda c: c["codigo"])
    pagina = Paginator(filas, 50).get_page(request.GET.get("page"))
    pagina_detalle = Paginator(detalle, 50).get_page(request.GET.get("page_detalle"))
    parametros = request.GET.copy()
    parametros.pop("page", None)
    parametros_detalle = request.GET.copy()
    parametros_detalle.pop("page_detalle", None)
    return render(request, "revisiones/mantenimientos_preventivos.html", {
        "pagina": pagina, "pagina_detalle": pagina_detalle,
        "cuenta_seleccionada": cuentas.get(cuenta_seleccionada),
        "q": q, "situacion": filtro, "querystring": parametros.urlencode(),
        "query_detalle": parametros_detalle.urlencode(),
        "total_cuentas": len(filas),
        "con_preventivo": sum(c["ultimo"] is not None for c in filas),
        "sin_preventivo": sum(c["ultimo"] is None for c in filas),
        "con_pendientes": sum(c["pendientes"] > 0 for c in filas),
    })
