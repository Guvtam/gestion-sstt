"""Actualización atómica de catálogo y su proyección de clasificación en ODT."""
from django.db import transaction
from .autorizacion import exigir_permiso_operativo
from ..dominio.administracion_cuentas import (
    CuentaActualizada, CuentaNoEncontrada, validar_actualizacion,
)
from ..dominio.cuentas import normalizar_codigo_cuenta
from ..models import CatalogoCuenta, ODT


def actualizar_cuenta(usuario, *, cuenta_id, tipo, ceco, observaciones):
    exigir_permiso_operativo(usuario, "revisiones.administrar_cuentas_sstt")
    tipo, ceco, observaciones = validar_actualizacion(tipo, ceco, observaciones)
    with transaction.atomic():
        try:
            cuenta = CatalogoCuenta.objects.select_for_update().get(pk=cuenta_id)
        except CatalogoCuenta.DoesNotExist:
            raise CuentaNoEncontrada("Cuenta no encontrada.") from None
        cuenta.tipo_cliente = tipo
        cuenta.ceco = ceco
        cuenta.observaciones = observaciones
        cuenta.requiere_revision_ceco = not bool(ceco)
        cuenta.actualizado_por = usuario
        cuenta.save()
        codigo_objetivo = cuenta.codigo_cuenta.strip().upper()
        lote, cantidad = [], 0
        for odt in ODT.objects.only("id", "cuenta_completa", "tipo_cliente").iterator(chunk_size=1000):
            if normalizar_codigo_cuenta(odt.cuenta_completa) == codigo_objetivo and odt.tipo_cliente != tipo:
                odt.tipo_cliente = tipo
                lote.append(odt)
            if len(lote) == 500:
                ODT.objects.bulk_update(lote, ["tipo_cliente"], batch_size=500)
                cantidad += len(lote)
                lote.clear()
        if lote:
            ODT.objects.bulk_update(lote, ["tipo_cliente"], batch_size=500)
            cantidad += len(lote)
        return CuentaActualizada(cuenta.codigo_cuenta, cantidad)
