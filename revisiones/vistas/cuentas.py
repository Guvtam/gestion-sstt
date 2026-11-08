"""Vistas HTTP de cuentas. Sin cambios de reglas de negocio."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import redirect, render
from django.http import Http404
from django.views.decorators.http import require_POST
from ..casos_uso.cuentas import actualizar_cuenta
from ..dominio.administracion_cuentas import CuentaInvalida, CuentaNoEncontrada
from ..models import CatalogoCuenta


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

    try:
        resultado = actualizar_cuenta(
            request.user, cuenta_id=cuenta_id,
            tipo=request.POST.get("tipo_cliente", ""),
            ceco=request.POST.get("ceco", ""),
            observaciones=request.POST.get("observaciones", ""),
        )
    except CuentaInvalida as error:
        messages.error(request, str(error))
        return redirect("administrar_cuentas")
    except CuentaNoEncontrada:
        raise Http404("Cuenta no encontrada.") from None
    messages.success(
        request,
        f"Cuenta {resultado.codigo} actualizada. {resultado.odts_actualizadas} ODT sincronizadas.",
    )
    return redirect("administrar_cuentas")
