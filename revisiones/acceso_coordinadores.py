"""Acceso de coordinadores: bandeja y operaciones de sus ODT."""
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin
from .coordinadores_softguard import COORDINADORES_SOFTGUARD, identificar_coordinador_odt


def datos_coordinador(user):
    usuario = user.get_username().strip().casefold()
    return next((d for d in COORDINADORES_SOFTGUARD.values()
                 if d["usuario"].casefold() == usuario), None)


def es_coordinador_sstt(user):
    if not user.is_authenticated or user.is_superuser:
        return False
    if user.get_username().strip().casefold() in ("admin", "jiturriaga"):
        return False
    return (datos_coordinador(user) is not None or user.groups.filter(
        name__in=("Coordinador", "Coordinadores SSTT")).exists())


def coordinador_visible(request, numero):
    datos = datos_coordinador(request.user)
    if datos is None:
        raise PermissionDenied("El usuario del coordinador no está vinculado a SoftGuard.")
    cache = getattr(request, "_coordinadores_sstt", None)
    if cache is None:
        cache = request._coordinadores_sstt = {}
    if numero not in cache:
        cache[numero] = identificar_coordinador_odt(numero)
    info = cache[numero]
    return (bool(info.get("identificado", False))
            and info.get("usuario") == datos["usuario"])


def limitar_odts_coordinador(request, registros):
    if not es_coordinador_sstt(request.user):
        return registros
    numeros = [n for n in registros.order_by().values_list("numero", flat=True).iterator()
               if coordinador_visible(request, n)]
    return registros.filter(numero__in=numeros)


class AccesoCoordinadorMiddleware(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        if not es_coordinador_sstt(request.user):
            return None
        nombre = request.resolver_match.url_name
        if nombre in ("login", "logout"):
            return None
        if datos_coordinador(request.user) is None:
            raise PermissionDenied(
                "Configura el nombre de usuario como jtapia, jbicz, yramirez o rsilva.")
        if nombre in ("bandeja", "contratistas_disponibles_ajax"):
            return None
        # Operaciones internas de la bandeja, no páginas adicionales.
        if nombre in ("historial_odt", "actualizar_informe", "cambiar_estado_correccion"):
            try:
                numero = int(view_kwargs.get("numero") or request.POST.get("numero", ""))
            except (TypeError, ValueError):
                return JsonResponse({"error": "Número de ODT inválido."}, status=400)
            try:
                permitido = coordinador_visible(request, numero)
            except Exception:
                return JsonResponse({"error": "No se pudo verificar el coordinador en SQL."}, status=503)
            if not permitido:
                raise PermissionDenied("Esta ODT pertenece a otro coordinador.")
            return None
        if request.method in ("GET", "HEAD"):
            return redirect("bandeja")
        raise PermissionDenied("El perfil Coordinador solo tiene acceso a la bandeja.")
