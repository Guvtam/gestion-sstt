from datetime import date
"""Consulta de preventivos desde la última sincronización local de ODT."""
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET
from .models import ODT, CatalogoCuenta
from .cuentas_utils import normalizar_codigo_cuenta, tipo_cliente_cuenta
from .dominio.servicios import SERVICIOS_PREVENTIVOS
from .consultas.preventivos import preventivos as consultar_preventivos


from .dominio.fechas import sumar_meses


@login_required
@permission_required("revisiones.ver_bandeja_sstt", raise_exception=True)
@require_GET
def mantenimientos_preventivos(request):
    q = request.GET.get("q", "").strip()
    filtro = request.GET.get("situacion", "").strip()
    cuenta_seleccionada = request.GET.get("cuenta", "").strip().upper()
    errores = []
    def fecha_filtro(nombre):
        texto = request.GET.get(nombre, "").strip()
        if not texto:
            return None
        try:
            return date.fromisoformat(texto)
        except ValueError:
            errores.append("Ingresa una fecha válida.")
            return None
    fecha_desde = fecha_filtro("fecha_desde")
    fecha_hasta = fecha_filtro("fecha_hasta")
    if fecha_desde and fecha_hasta and fecha_desde > fecha_hasta:
        errores.append("La fecha desde debe ser anterior o igual a la fecha hasta.")
    campo_fecha = request.GET.get("campo_fecha", "ultimo")
    if campo_fecha not in ("ultimo", "proximo"):
        campo_fecha = "ultimo"
    hoy = timezone.localdate()
    cuentas = {}
    for cuenta in CatalogoCuenta.objects.all().iterator(chunk_size=1000):
        codigo = normalizar_codigo_cuenta(cuenta.codigo_cuenta)
        if not codigo:
            continue
        cuentas[codigo] = {
            "codigo": codigo, "nombre": cuenta.nombre_cuenta,
            "tipo_cliente": tipo_cliente_cuenta(codigo, {codigo: cuenta}), "ceco": cuenta.ceco,
            "cantidad": 0, "pendientes": 0, "ultimo": None,
        }
    # Incorporar cuentas que aún no estén registradas en el catálogo.
    for texto in ODT.objects.order_by().values_list("cuenta_completa", flat=True).distinct().iterator(chunk_size=1000):
        codigo = normalizar_codigo_cuenta(texto)
        if codigo in cuentas and not cuentas[codigo]["nombre"]:
            cuentas[codigo]["nombre"] = texto
        if codigo and codigo not in cuentas:
            cuentas[codigo] = {"codigo": codigo, "nombre": texto, "tipo_cliente": tipo_cliente_cuenta(codigo, {}),
                              "ceco": "", "cantidad": 0, "pendientes": 0, "ultimo": None}

    preventivos = consultar_preventivos().order_by("-fecha_finalizacion", "-numero")
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
        fecha_ultimo = timezone.localtime(ultimo.fecha_finalizacion).date() if ultimo else None
        cuenta["proximo"] = sumar_meses(fecha_ultimo, 6) if fecha_ultimo else None
        cuenta["vencido"] = bool(cuenta["proximo"] and cuenta["proximo"] < hoy)
        fecha_objetivo = cuenta["proximo"] if campo_fecha == "proximo" else fecha_ultimo
        if errores:
            continue
        if (fecha_desde or fecha_hasta) and fecha_objetivo is None:
            continue
        if fecha_desde and fecha_objetivo < fecha_desde:
            continue
        if fecha_hasta and fecha_objetivo > fecha_hasta:
            continue
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
        "fecha_desde": request.GET.get("fecha_desde", ""),
        "fecha_hasta": request.GET.get("fecha_hasta", ""), "campo_fecha": campo_fecha,
        "errores": errores,
        "cuenta_seleccionada": cuentas.get(cuenta_seleccionada),
        "q": q, "situacion": filtro, "querystring": parametros.urlencode(),
        "query_detalle": parametros_detalle.urlencode(),
        "total_cuentas": len(filas),
        "con_preventivo": sum(c["ultimo"] is not None for c in filas),
        "sin_preventivo": sum(c["ultimo"] is None for c in filas),
        "con_pendientes": sum(c["pendientes"] > 0 for c in filas),
    })
