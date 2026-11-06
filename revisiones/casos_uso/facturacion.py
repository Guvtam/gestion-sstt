"""Previsualización y confirmación transaccional con comprobación de lo revisado."""
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json

from django.conf import settings
from django.core import signing
from django.db import IntegrityError, transaction

from ..consultas.facturacion import odts_facturables
from ..dominio.facturacion import FacturacionInvalida, FacturacionNoEncontrada
from ..dominio.servicios import servicio_efectivo
from ..facturacion_models import FacturacionContratista, FacturacionODT, PeriodoFacturacion
from .autorizacion import exigir_permiso_operativo

PERMISO = "revisiones.exportar_pagos_sstt"
SALT = "sstt.confirmar-facturacion.v1"
CAMPOS = (
    "id", "numero", "contratista", "servicio", "servicio_editado", "valor_pago_tecnico",
    "valor_pago_editado", "fecha_finalizacion", "cuenta_completa",
)


@dataclass(frozen=True)
class Previsualizacion:
    resumen: list
    cantidad: int
    confirmacion: str


@dataclass(frozen=True)
class FacturacionConfirmada:
    periodo_id: int
    cantidad_odt: int
    cantidad_contratistas: int


@dataclass(frozen=True)
class RequisicionActualizada:
    id: int
    periodo_id: int
    contratista: str
    numero: str


def _monto(odt):
    valor = odt.valor_pago_tecnico if odt.valor_pago_editado is None else odt.valor_pago_editado
    return valor if valor is not None else Decimal("0")


def _huella_y_resumen(filas):
    huella = hashlib.sha256()
    grupos = defaultdict(lambda: {"cantidad": 0, "monto": Decimal("0")})
    cantidad = 0
    for odt in filas:
        monto = _monto(odt)
        contenido = (
            odt.pk, odt.numero, odt.contratista, servicio_efectivo(odt.servicio, odt.servicio_editado),
            format(monto, ".2f"), odt.fecha_finalizacion.isoformat(), odt.cuenta_completa,
        )
        huella.update(json.dumps(contenido, ensure_ascii=True, separators=(",", ":")).encode())
        huella.update(b"\n")
        grupos[odt.contratista]["cantidad"] += 1
        grupos[odt.contratista]["monto"] += monto
        cantidad += 1
    resumen = [{"contratista": nombre, **datos} for nombre, datos in sorted(grupos.items())]
    return huella.hexdigest(), resumen, cantidad


def previsualizar(usuario, seleccion):
    exigir_permiso_operativo(usuario, PERMISO)
    pendientes = odts_facturables(seleccion).filter(item_facturacion__isnull=True)
    # Resumen y firma salen de una misma lectura, sin carreras entre dos consultas.
    huella, resumen, cantidad = _huella_y_resumen(
        pendientes.only(*CAMPOS).order_by("numero").iterator(chunk_size=500)
    )
    confirmacion = signing.dumps({
        "version": 1, "usuario": str(usuario.pk), "seleccion": seleccion.clave(),
        "huella": huella, "cantidad": cantidad,
    }, salt=SALT, compress=True)
    return Previsualizacion(resumen, cantidad, confirmacion)


def confirmar(usuario, seleccion, *, requisiciones, confirmacion):
    exigir_permiso_operativo(usuario, PERMISO)
    try:
        datos = signing.loads(
            confirmacion, salt=SALT,
            max_age=getattr(settings, "SSTT_CONFIRMACION_FACTURACION_SEGUNDOS", 1800),
        )
        valida = (datos.get("version") == 1 and datos.get("usuario") == str(usuario.pk)
                  and datos.get("seleccion") == seleccion.clave())
    except (signing.BadSignature, TypeError, ValueError, AttributeError):
        valida = False
    if not valida:
        raise FacturacionInvalida("La confirmación no es válida o venció. Actualiza la previsualización.")
    if not isinstance(requisiciones, dict):
        raise FacturacionInvalida("Las requisiciones no son válidas.")
    requisiciones = {nombre: str(valor or "").strip() for nombre, valor in requisiciones.items()}
    for nombre, valor in requisiciones.items():
        if len(valor) > 100:
            raise FacturacionInvalida(f"La requisición de {nombre} supera los 100 caracteres.")

    try:
        with transaction.atomic():
            odts = list(odts_facturables(seleccion).filter(item_facturacion__isnull=True)
                        .only(*CAMPOS).order_by("numero").select_for_update(of=("self",)))
            if not odts:
                raise FacturacionInvalida("Ya no quedan ODT pendientes para facturar.")
            huella, _, cantidad = _huella_y_resumen(odts)
            if huella != datos.get("huella") or cantidad != datos.get("cantidad"):
                raise FacturacionInvalida("La selección, los servicios o los montos cambiaron. Actualiza la previsualización.")
            if {odt.contratista for odt in odts} != set(requisiciones):
                raise FacturacionInvalida("Los contratistas cambiaron. Actualiza la previsualización.")
            periodo, _ = PeriodoFacturacion.objects.get_or_create(
                fecha_desde=seleccion.desde, fecha_hasta=seleccion.hasta, defaults={"creado_por": usuario},
            )
            PeriodoFacturacion.objects.select_for_update().get(pk=periodo.pk)
            facturaciones = {}
            for nombre in sorted(requisiciones):
                factura, _ = FacturacionContratista.objects.get_or_create(
                    periodo=periodo, contratista=nombre,
                    defaults={"numero_requisicion": requisiciones[nombre], "creado_por": usuario},
                )
                facturaciones[nombre] = factura
            if FacturacionODT.objects.filter(odt__in=odts).exists():
                raise FacturacionInvalida("Se detectaron ODT ya facturadas. Actualiza la previsualización.")
            FacturacionODT.objects.bulk_create([
                FacturacionODT(
                    facturacion=facturaciones[odt.contratista], odt=odt,
                    servicio_facturado=servicio_efectivo(odt.servicio, odt.servicio_editado),
                    monto_facturado=_monto(odt),
                ) for odt in odts
            ], batch_size=500)
            return FacturacionConfirmada(periodo.pk, len(odts), len(facturaciones))
    except IntegrityError:
        raise FacturacionInvalida("La selección cambió durante la operación. Actualiza la previsualización.") from None


def actualizar_requisicion(usuario, *, facturacion_id, numero):
    exigir_permiso_operativo(usuario, PERMISO)
    numero = str(numero or "").strip()
    if len(numero) > 100:
        raise FacturacionInvalida("La requisición no puede superar los 100 caracteres.")
    with transaction.atomic():
        try:
            factura = FacturacionContratista.objects.select_for_update().get(pk=facturacion_id)
        except FacturacionContratista.DoesNotExist:
            raise FacturacionNoEncontrada("Facturación no encontrada.") from None
        if factura.numero_requisicion != numero:
            factura.numero_requisicion = numero
            factura.save(update_fields=["numero_requisicion"])
        return RequisicionActualizada(factura.pk, factura.periodo_id, factura.contratista, numero)
