"""Autorización compartida de permisos y alcance por coordinador."""
from django.core.exceptions import PermissionDenied

from ..acceso_coordinadores import datos_coordinador, es_coordinador_sstt
from ..coordinadores_softguard import identificar_coordinadores_odt
from ..dominio.errores import VerificacionCoordinadorFallida


def exigir_permiso(usuario, permiso):
    if (not usuario.is_authenticated or not usuario.is_active or not usuario.has_perm(permiso)):
        raise PermissionDenied("No tienes permiso para realizar esta operación.")


def exigir_alcance_coordinador(usuario, numero, resolver=None):
    if not es_coordinador_sstt(usuario):
        return
    datos = datos_coordinador(usuario)
    if datos is None:
        raise PermissionDenied("El usuario del coordinador no está vinculado a SoftGuard.")
    try:
        info = resolver(numero) if resolver else identificar_coordinadores_odt([numero])[numero]
        if (not isinstance(info, dict) or not isinstance(info.get("identificado"), bool)
                or info.get("disponible", True) is False):
            raise ValueError("Respuesta de responsable inválida")
    except Exception:
        raise VerificacionCoordinadorFallida("No se pudo verificar el coordinador en SQL.") from None
    if info["identificado"] is not True or info.get("usuario") != datos["usuario"]:
        raise PermissionDenied("Esta ODT pertenece a otro coordinador o no tiene responsable identificado.")


def exigir_permiso_operativo(usuario, permiso):
    exigir_permiso(usuario, permiso)
    if es_coordinador_sstt(usuario):
        raise PermissionDenied("No tienes permiso para realizar esta operación.")
