"""Editar correcciones de ODT y revisar pagos sin depender de vistas HTTP."""
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction

from ..correcciones import registrar_cambio_manual
from ..dominio.errores import DatosODTInvalidos, ODTBloqueada, ODTNoEncontrada
from ..dominio.pagos import estado_pago_efectivo, motivo_bloqueo
from ..dominio.servicios import SERVICIOS_PRINCIPALES, servicio_efectivo
from ..dominio.validacion_odt import estado_revision, importe_pago, numero_odt, servicio_obligatorio, texto
from ..facturacion_models import FacturacionODT
from ..models import EventoRevision, ODT, Revision
from .autorizacion import exigir_permiso_operativo as _autorizar


@dataclass(frozen=True)
class ResultadoEdicion:
    monto: Decimal
    estado: str
    cambio: bool


@dataclass(frozen=True)
class ResultadoRevision:
    estado: str
    cambio: bool




def _bloquear_odts(numeros):
    odts = list(ODT.objects.select_for_update().filter(numero__in=numeros).order_by("numero"))
    if len(odts) != len(numeros):
        raise ODTNoEncontrada("Algunas ODT seleccionadas no existen.")
    revisiones = Revision.objects.select_for_update().in_bulk([o.pk for o in odts], field_name="odt_id")
    facturadas = set(FacturacionODT.objects.filter(odt__in=odts).values_list("odt_id", flat=True))
    for odt in odts:
        revision = revisiones.get(odt.pk)
        bloqueo = motivo_bloqueo(
            facturada=odt.pk in facturadas, rechazada=revision is not None and revision.estado == "RECHAZADA",
        )
        if bloqueo:
            raise ODTBloqueada(f"ODT {odt.numero}: {bloqueo}" if len(numeros) > 1 else bloqueo)
    return odts, revisiones


def editar_odt(usuario, *, numero, servicio, monto, confirmar_monto=False, comentario=""):
    _autorizar(usuario, "revisiones.editar_odt_sstt")
    numero = numero_odt(numero)
    servicio, monto = servicio_obligatorio(servicio), importe_pago(monto)
    comentario = texto(comentario)
    with transaction.atomic():
        odts, revisiones = _bloquear_odts([numero])
        odt = odts[0]
        revision = revisiones.get(odt.pk)
        estado = estado_pago_efectivo(revision.estado if revision else None)
        anterior_servicio = servicio_efectivo(odt.servicio, odt.servicio_editado)
        anterior_monto = odt.valor_pago_tecnico if odt.valor_pago_editado is None else odt.valor_pago_editado
        cambio_servicio, cambio_monto = servicio != anterior_servicio, monto != anterior_monto
        if cambio_servicio and servicio not in SERVICIOS_PRINCIPALES:
            raise DatosODTInvalidos("Selecciona uno de los cuatro servicios principales.")
        if cambio_monto and confirmar_monto is not True:
            raise DatosODTInvalidos("Debes confirmar expresamente el cambio de monto.")
        if not (cambio_servicio or cambio_monto):
            return ResultadoEdicion(monto, estado, False)

        odt.servicio_editado = servicio if servicio != odt.servicio else None
        odt.valor_pago_editado = monto if monto != odt.valor_pago_tecnico else None
        odt.modificado_manualmente = odt.servicio_editado is not None or odt.valor_pago_editado is not None
        odt.save(update_fields=["servicio_editado", "valor_pago_editado", "modificado_manualmente"])
        registrar_cambio_manual(odt, usuario)
        cambios = []
        if cambio_servicio:
            cambios.append(f"Servicio: {anterior_servicio} → {servicio}")
        if cambio_monto:
            cambios.append(f"Pago técnico: ${anterior_monto} → ${monto}")
        if comentario:
            cambios.append(f"Motivo: {comentario}")
        EventoRevision.objects.create(
            odt=odt, estado_anterior=estado, estado_nuevo=estado,
            comentario=" | ".join(cambios), usuario=usuario,
        )
        return ResultadoEdicion(monto, estado, True)


def _guardar_revision(odt, revision, estado, comentario, usuario):
    anterior = estado_pago_efectivo(revision.estado if revision else None)
    if anterior == estado:
        return False
    if revision is None:
        revision = Revision(odt=odt)
    revision.estado = estado
    revision.observacion = comentario
    revision.actualizado_por = usuario
    revision.save()
    EventoRevision.objects.create(
        odt=odt, estado_anterior=anterior, estado_nuevo=estado,
        comentario=f"Revisión: {anterior} → {estado}" + (f" | Motivo: {comentario}" if comentario else ""),
        usuario=usuario,
    )
    return True


def revisar_odt(usuario, *, numero, estado, comentario=""):
    _autorizar(usuario, "revisiones.revisar_pago_sstt")
    numero = numero_odt(numero, formateado=True)
    estado, comentario = estado_revision(estado, comentario)
    with transaction.atomic():
        odts, revisiones = _bloquear_odts([numero])
        odt = odts[0]
        cambio = _guardar_revision(odt, revisiones.get(odt.pk), estado, comentario, usuario)
        return ResultadoRevision(estado, cambio)


def revisar_odts(usuario, *, numeros, estado, comentario=""):
    _autorizar(usuario, "revisiones.revisar_pago_sstt")
    estado, comentario = estado_revision(estado, comentario)
    if numeros is None or isinstance(numeros, (str, bytes, dict)):
        raise DatosODTInvalidos("Selecciona entre 1 y 300 ODT.")
    try:
        numeros = iter(numeros)
    except TypeError:
        raise DatosODTInvalidos("Selecciona entre 1 y 300 ODT.") from None
    seleccion = set()
    for indice, numero in enumerate(numeros):
        seleccion.add(numero_odt(numero))
        if len(seleccion) > 300 or indice >= 1000:
            raise DatosODTInvalidos("Selecciona entre 1 y 300 ODT.")
    if not seleccion:
        raise DatosODTInvalidos("Selecciona entre 1 y 300 ODT.")
    with transaction.atomic():
        odts, revisiones = _bloquear_odts(seleccion)
        return sum(_guardar_revision(odt, revisiones.get(odt.pk), estado, comentario, usuario) for odt in odts)
