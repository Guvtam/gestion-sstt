"""Autorización de operaciones reservadas a perfiles operativos no coordinadores."""
from django.core.exceptions import PermissionDenied

from ..acceso_coordinadores import es_coordinador_sstt


def exigir_permiso_operativo(usuario, permiso):
    if (not usuario.is_authenticated or not usuario.is_active
            or not usuario.has_perm(permiso) or es_coordinador_sstt(usuario)):
        raise PermissionDenied("No tienes permiso para realizar esta operación.")
