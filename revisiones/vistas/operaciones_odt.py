"""Vistas HTTP de operaciones odt. Sin cambios de reglas de negocio."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.http import JsonResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_POST
from ..acceso_coordinadores import (
    coordinador_visible,
    coordinadores_en_peticion,
)
from ..casos_uso.gestion_correcciones import gestionar_correccion
from ..casos_uso.edicion_odt import editar_odt, revisar_odt, revisar_odts
from ..casos_uso.informes_asignaciones import actualizar_estado_informe, asignar_responsable
from ..coordinadores_softguard import identificar_coordinador_softguard
from ..dominio.errores import ErrorOperacionODT
from ..dominio.pagos import OPCIONES_BANDEJA
from .respuestas import _respuesta_error_odt


@login_required
@permission_required("revisiones.revisar_pago_sstt", raise_exception=True)
@require_POST
def acciones(request):
    """Adaptador HTML para revisión múltiple; toda escritura vive en el caso de uso."""
    try:
        cantidad = revisar_odts(
            request.user, numeros=request.POST.getlist("odts"),
            estado=request.POST.get("nuevo_estado", ""), comentario=request.POST.get("comentario", ""),
        )
    except ErrorOperacionODT as error:
        messages.error(request, str(error))
    else:
        nombre = dict(OPCIONES_BANDEJA)[request.POST.get("nuevo_estado", "").strip()]
        messages.success(request, f"{cantidad} ODT actualizadas a {nombre}.")
    return redirect("bandeja")



@login_required
@permission_required("revisiones.editar_odt_sstt", raise_exception=True)
@require_POST
def guardar_fila(request):
    """Editar no cambia el estado de pago: se conserva el endpoint independiente."""
    if request.POST.get("estado", "APROBADA").strip() not in dict(OPCIONES_BANDEJA):
        return JsonResponse({"error": "Estado de revisión inválido."}, status=400)
    try:
        resultado = editar_odt(
            request.user, numero=request.POST.get("numero", ""),
            servicio=request.POST.get("servicio", ""), monto=request.POST.get("monto", ""),
            confirmar_monto=request.POST.get("confirmar_monto") == "SI",
            comentario=request.POST.get("comentario", ""),
        )
    except ErrorOperacionODT as error:
        return _respuesta_error_odt(error)
    return JsonResponse({
        "ok": True,
        "mensaje": "Cambios guardados correctamente." if resultado.cambio else "No hay cambios para guardar.",
        "monto": str(resultado.monto), "estado": resultado.estado,
    })



@login_required
@permission_required("revisiones.revisar_pago_sstt", raise_exception=True)
@require_POST
def actualizar_revision(request):
    try:
        resultado = revisar_odt(
            request.user, numero=request.POST.get("numero", ""),
            estado=request.POST.get("estado", ""), comentario=request.POST.get("comentario", ""),
        )
    except ErrorOperacionODT as error:
        return _respuesta_error_odt(error)
    return JsonResponse({
        "ok": True,
        "mensaje": "Estado de revisión actualizado." if resultado.cambio else "El estado no ha cambiado.",
        "estado": resultado.estado,
    })



@login_required
@permission_required("revisiones.cambiar_informe_sstt", raise_exception=True)
@require_POST
def actualizar_informe(request):
    try:
        resultado = actualizar_estado_informe(
            request.user, numero=request.POST.get("numero", ""), estado=request.POST.get("estado", ""),
            resolver_responsable=lambda n: coordinadores_en_peticion(request, [n])[n],
        )
    except ErrorOperacionODT as error:
        return _respuesta_error_odt(error)
    return JsonResponse({
        "ok": True, "estado": resultado.estado,
        "mensaje": "Estado de informe actualizado." if resultado.cambio else "Sin cambios.",
    })



@login_required
@require_POST
def cambiar_estado_correccion(request):
    try:
        resultado = gestionar_correccion(
            request.user, numero=request.POST.get("numero", ""),
            estado=request.POST.get("estado", ""),
            verificar_alcance=lambda n: coordinador_visible(request, n),
        )
    except ErrorOperacionODT as error:
        return _respuesta_error_odt(error)
    return JsonResponse({"ok": True, "estado": resultado.estado})



@login_required
@require_POST
def asignar_coordinador(request):
    try:
        resultado = asignar_responsable(
            request.user, numero=request.POST.get("numero", ""), coordinador=request.POST.get("coordinador", ""),
            verificar_origen=identificar_coordinador_softguard,
        )
    except ErrorOperacionODT as error:
        return _respuesta_error_odt(error)
    return JsonResponse({"ok": True, "coordinador": resultado.nombre})

