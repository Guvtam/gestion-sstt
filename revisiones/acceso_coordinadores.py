"""Acceso de coordinadores: bandeja, calendario propio y operaciones de sus ODT."""
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin
from .coordinadores_softguard import (
    COORDINADORES_SOFTGUARD, catalogo_coordinadores, CoordinadoresNoDisponibles, identificar_coordinadores_odt,
)
from .dominio.validacion_odt import numero_odt
from .dominio.errores import DatosODTInvalidos


def coordinadores_en_peticion(request, numeros):
    """Datos, nunca decisiones de permiso, reutilizados solo en esta petición."""
    numeros = list(dict.fromkeys(numero_odt(n) for n in numeros))
    cache = getattr(request, "_coordinadores_sstt", None)
    if cache is None:
        cache = request._coordinadores_sstt = {}
    pendientes = [n for n in numeros if n not in cache]
    for inicio in range(0, len(pendientes), 250):
        lote = pendientes[inicio:inicio+250]
        try:
            resultados = identificar_coordinadores_odt(lote)
        except CoordinadoresNoDisponibles as error:
            cache.update(error.confirmados)
            raise
        if set(resultados) != set(lote):
            raise CoordinadoresNoDisponibles()
        cache.update(resultados)
    return {n: cache[n] for n in numeros}


def coordinadores_para_mostrar(request, numeros):
    """Solo presentación; nunca usar este fallback para autorizar o filtrar."""
    numeros = list(numeros)
    try:
        return coordinadores_en_peticion(request, numeros)
    except CoordinadoresNoDisponibles:
        cache = getattr(request, "_coordinadores_sstt", {})
        return {n: cache.get(n, {
            "nombre": "No disponible", "usuario": None,
            "identificado": False, "disponible": False,
        }) for n in numeros}


def _vinculo_coordinador(user):
    """Cache de datos en la instancia de usuario de esta petición, no global."""
    if not user.is_authenticated or user.pk is None:
        return None
    if not hasattr(user, "_vinculo_coordinador_sstt"):
        from .models import VinculoCoordinador
        user._vinculo_coordinador_sstt = VinculoCoordinador.objects.filter(
            usuario_id=user.pk).first()
    return user._vinculo_coordinador_sstt


def datos_coordinador(user):
    if not user.is_authenticated:
        return None
    vinculo = _vinculo_coordinador(user)
    if vinculo is not None:
        if not vinculo.activo:
            return None
        usuario = vinculo.usuario_softguard
    else:
        # Compatibilidad con las cuentas actuales hasta configurar su vínculo.
        usuario = user.get_username().strip().casefold()
    if not hasattr(user, "_catalogo_coordinador_sstt"):
        user._catalogo_coordinador_sstt = catalogo_coordinadores()
    return next((d for d in user._catalogo_coordinador_sstt.values()
                 if d["usuario"].casefold() == usuario), None)


def _identidad_restringida(user):
    usuario = user.get_username().strip().casefold()
    if any(d["usuario"] == usuario for d in COORDINADORES_SOFTGUARD.values()):
        return True
    from .models import ResponsableSoftGuard
    return ResponsableSoftGuard.objects.filter(usuario_softguard__iexact=usuario).exists()


def es_coordinador_sstt(user):
    if not user.is_authenticated or user.is_superuser:
        return False
    if user.get_username().strip().casefold() in ("admin", "jiturriaga"):
        return False
    return (_vinculo_coordinador(user) is not None or datos_coordinador(user) is not None or _identidad_restringida(user) or user.groups.filter(
        name__in=("Coordinador", "Coordinadores SSTT")).exists())


def coordinador_visible(request, numero):
    datos = datos_coordinador(request.user)
    if datos is None:
        raise PermissionDenied("El usuario del coordinador no está vinculado a SoftGuard.")
    numero = numero_odt(numero)
    info = coordinadores_en_peticion(request, [numero])[numero]
    return (bool(info.get("identificado", False))
            and info.get("usuario") == datos["usuario"])


def limitar_odts_coordinador(request, registros):
    if not es_coordinador_sstt(request.user):
        return registros
    datos = datos_coordinador(request.user)
    if datos is None:
        raise PermissionDenied("El usuario del coordinador no está vinculado a SoftGuard.")
    responsables = coordinadores_en_peticion(
        request, registros.order_by().values_list("numero", flat=True).iterator(),
    )
    numeros = [n for n, info in responsables.items()
               if info.get("identificado", False) and info.get("usuario") == datos["usuario"]]
    return registros.filter(numero__in=numeros)


class AccesoCoordinadorMiddleware(MiddlewareMixin):
    def process_exception(self, request, exception):
        if isinstance(exception, CoordinadoresNoDisponibles):
            return JsonResponse({"error": str(exception)}, status=503)
        return None

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not es_coordinador_sstt(request.user):
            return None
        nombre = request.resolver_match.url_name
        if nombre in ("login", "logout"):
            return None
        if datos_coordinador(request.user) is None:
            raise PermissionDenied(
                "El vínculo de coordinador no está activo o no está configurado. Contacta a administración.")
        if nombre in ("bandeja", "contratistas_disponibles_ajax", "calendario_servicios"):
            return None
        # Operaciones internas de la bandeja, no páginas adicionales.
        if nombre in ("historial_odt", "actualizar_informe", "cambiar_estado_correccion"):
            try:
                numero = numero_odt(view_kwargs.get("numero") or request.POST.get("numero", ""))
            except (DatosODTInvalidos, TypeError, ValueError):
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
        raise PermissionDenied("El perfil Coordinador solo tiene acceso a la bandeja y su calendario de visitas.")
