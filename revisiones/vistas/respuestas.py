"""Vistas HTTP de respuestas. Sin cambios de reglas de negocio."""
from django.http import Http404, JsonResponse
from ..dominio.errores import ODTBloqueada, ODTNoEncontrada, VerificacionCoordinadorFallida


def _respuesta_error_odt(error):
    if isinstance(error, ODTNoEncontrada):
        raise Http404("ODT no encontrada.") from None
    if isinstance(error, VerificacionCoordinadorFallida):
        estado = 503
    elif isinstance(error, ODTBloqueada):
        estado = 409
    else:
        estado = 400
    return JsonResponse({"error": str(error)}, status=estado)

