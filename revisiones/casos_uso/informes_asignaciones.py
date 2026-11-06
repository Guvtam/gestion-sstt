"""Operaciones transaccionales de informe y asignación, sin dependencia de HTTP."""
from dataclasses import dataclass

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from ..coordinadores_softguard import (
    COORDINADORES_SOFTGUARD, catalogo_coordinadores, identificar_coordinador_softguard, puede_asignar_coordinador,
)
from ..dominio.errores import (
    DatosODTInvalidos, ODTBloqueada, ODTNoEncontrada, VerificacionCoordinadorFallida,
)
from ..dominio.pagos import estado_pago_efectivo
from ..dominio.validacion_odt import numero_odt, texto
from ..models import AsignacionCoordinadorODT, EventoRevision, ODT, Revision
from .autorizacion import exigir_alcance_coordinador, exigir_permiso
from .bloqueos_odt import cargar_odts_editables


@dataclass(frozen=True)
class ResultadoInforme:
    estado: str
    cambio: bool


@dataclass(frozen=True)
class ResultadoAsignacion:
    numero: int
    nombre: str


def actualizar_estado_informe(usuario, *, numero, estado, resolver_responsable=None):
    exigir_permiso(usuario, "revisiones.cambiar_informe_sstt")
    numero, estado = numero_odt(numero), texto(estado)
    validos = dict(ODT.ESTADOS_INFORME)
    if estado not in validos:
        raise DatosODTInvalidos("Estado de informe inválido.")
    # Fuera de la transacción de escritura: la verificación puede consultar el origen.
    exigir_alcance_coordinador(usuario, numero, resolver_responsable)
    with transaction.atomic():
        odts, revisiones = cargar_odts_editables([numero])
        odt = odts[0]
        anterior = odt.estado_informe
        if anterior == estado:
            return ResultadoInforme(estado, False)
        odt.estado_informe = estado
        odt.informe_actualizado_por = usuario
        odt.informe_actualizado_en = timezone.now()
        odt.save(update_fields=["estado_informe", "informe_actualizado_por", "informe_actualizado_en"])
        revision = revisiones.get(odt.pk)
        pago = estado_pago_efectivo(revision.estado if revision else None)
        EventoRevision.objects.create(
            odt=odt, estado_anterior=pago, estado_nuevo=pago,
            comentario=f"Informe: {validos.get(anterior, anterior)} → {validos[estado]}", usuario=usuario,
        )
        return ResultadoInforme(estado, True)


def asignar_responsable(usuario, *, numero, coordinador, verificar_origen=None):
    if not puede_asignar_coordinador(usuario):
        raise PermissionDenied("Solo admin y jiturriaga pueden asignar coordinadores.")
    numero, coordinador = numero_odt(numero), texto(coordinador)
    datos = next((d for d in catalogo_coordinadores().values() if d["usuario"] == coordinador), None)
    if datos is None:
        raise DatosODTInvalidos("Coordinador inválido.")
    odt_id = ODT.objects.filter(numero=numero).values_list("pk", flat=True).first()
    if odt_id is None:
        raise ODTNoEncontrada("ODT no encontrada.")
    if AsignacionCoordinadorODT.objects.filter(odt_id=odt_id).exists():
        raise ODTBloqueada("La ODT ya tiene un coordinador asignado.")
    try:
        verificar = verificar_origen or identificar_coordinador_softguard
        info = verificar(numero)
        if not isinstance(info, dict) or not isinstance(info.get("identificado"), bool):
            raise ValueError("Respuesta de responsable inválida")
    except Exception:
        raise VerificacionCoordinadorFallida("No se pudo verificar el coordinador en SoftGuard.") from None
    if info["identificado"]:
        raise ODTBloqueada("La ODT ya tiene coordinador identificado. Actualiza la pantalla.")

    # Revalidar y bloquear localmente después de la lectura del origen. No hay
    # transacción distribuida con SoftGuard ni promesa de congelar su historial.
    with transaction.atomic():
        try:
            odt = ODT.objects.select_for_update().only("id", "numero").get(numero=numero)
        except ODT.DoesNotExist:
            raise ODTNoEncontrada("ODT no encontrada.") from None
        if AsignacionCoordinadorODT.objects.filter(odt=odt).exists():
            raise ODTBloqueada("La ODT ya tiene un coordinador asignado.")
        AsignacionCoordinadorODT.objects.create(
            odt=odt, usuario_coordinador=coordinador, asignado_por=usuario,
        )
        revision = Revision.objects.filter(odt=odt).first()
        estado = revision.estado if revision else "POR_REVISAR"
        EventoRevision.objects.create(
            odt=odt, estado_anterior=estado, estado_nuevo=estado, usuario=usuario,
            comentario=f"Coordinador asignado en SSTT: {datos['nombre']}",
        )
        return ResultadoAsignacion(numero, datos["nombre"])
