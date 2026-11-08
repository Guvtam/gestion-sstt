"""Vistas HTTP de odt. Sin cambios de reglas de negocio."""
from django.contrib.auth.decorators import login_required, permission_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from ..models import ODT, Revision
from ..servicios_sql import consultar_historial_odt


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

