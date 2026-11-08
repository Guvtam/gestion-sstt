"""Vistas HTTP de cuentas. Sin cambios de reglas de negocio."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from ..cuentas_utils import normalizar_codigo_cuenta
from ..models import CatalogoCuenta, ODT


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

