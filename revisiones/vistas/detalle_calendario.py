"""Consulta técnica de ODT visibles en el calendario de equipos internos."""
import logging
from urllib.parse import urlsplit
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models.functions import Lower, Trim
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from ..acceso_calendario import puede_ver_detalle_calendario, limitar_tecnicos_calendario
from ..acceso_coordinadores import limitar_odts_coordinador
from ..consultas.calendario import ESTADOS_VISITA
from ..dominio.detalle_tecnico import texto_tecnico, ADMINISTRATIVO
from ..dominio.servicios import servicio_efectivo
from ..models import ODT
from ..servicios_sql import consultar_historial_odt

logger = logging.getLogger(__name__)


def regreso_calendario(valor):
    destino = reverse("calendario_servicios")
    try:
        partes = urlsplit(valor or "")
    except ValueError:
        return destino
    if not partes.scheme and not partes.netloc and partes.path == destino:
        return destino + ("?" + partes.query if partes.query else "")
    return destino


def fecha_evento(valor):
    if not valor:
        return None
    fecha = parse_datetime(valor) if isinstance(valor, str) else valor
    if fecha is None:
        return None
    return timezone.make_aware(fecha) if timezone.is_naive(fecha) else fecha


@never_cache
@login_required
@require_GET
def detalle_calendario(request, numero):
    if not puede_ver_detalle_calendario(request.user):
        raise PermissionDenied("No tienes acceso al detalle técnico de este calendario.")
    consulta = ODT.objects.annotate(_estado_visita=Lower(Trim("estado_softguard"))).filter(
        numero=numero, fecha_visita__isnull=False, _estado_visita__in=ESTADOS_VISITA)
    consulta = limitar_tecnicos_calendario(request.user, limitar_odts_coordinador(request, consulta))
    # Autorizar antes de consultar SQL y antes de preparar cualquier dato de salida.
    odt = get_object_or_404(consulta, numero=numero)
    eventos = []
    historial_disponible = True
    try:
        for movimiento in consultar_historial_odt(odt.numero):
            accion = str(movimiento.get("Accion") or "")
            if ADMINISTRATIVO.search(accion):
                continue
            eventos.append({"fecha": fecha_evento(movimiento.get("FechaHora")),
                "accion": accion or "Observación",
                "observacion": texto_tecnico(movimiento.get("Observacion")),
                "usuario": texto_tecnico(movimiento.get("NombreUsuario") or "Usuario no identificado")})
        eventos.sort(key=lambda e: e["fecha"].timestamp() if e["fecha"] else float("-inf"), reverse=True)
    except Exception:
        logger.warning("No se pudo consultar historial técnico de ODT %s", odt.numero)
        eventos = []
        historial_disponible = False
    # Solo campos permitidos. No enviar el modelo ni auditorías financieras al template.
    detalle = {"numero": odt.numero, "cuenta": odt.cuenta_completa,
        "direccion": odt.direccion, "localidad": odt.localidad, "tecnico": odt.tecnico,
        "estado": odt.estado_softguard, "servicio": servicio_efectivo(odt.servicio, odt.servicio_editado),
        "fecha_creacion": odt.fecha_creacion, "fecha_visita": odt.fecha_visita,
        "fecha_finalizacion": odt.fecha_finalizacion, "observaciones": texto_tecnico(odt.observaciones_insumos)}
    return render(request, "revisiones/detalle_calendario.html", {"detalle": detalle,
        "eventos": eventos, "historial_disponible": historial_disponible,
        "volver_calendario": regreso_calendario(request.GET.get("volver"))})
