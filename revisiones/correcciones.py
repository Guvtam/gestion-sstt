from decimal import Decimal
from django.utils import timezone
from .models import CorreccionODT, EventoCorreccionODT


def coinciden(odt, seguimiento):
    servicio_ok = (not seguimiento.corrige_servicio or
        (odt.servicio or "").strip().casefold() == (seguimiento.servicio_objetivo or "").strip().casefold())
    monto_ok = (not seguimiento.corrige_monto or
        odt.valor_pago_tecnico == seguimiento.monto_objetivo)
    return servicio_ok and monto_ok


def registrar_cambio_manual(odt, usuario):
    """Llamar dentro de la transacción de guardar_fila, tras odt.save()."""
    seguimiento, creado = CorreccionODT.objects.select_for_update().get_or_create(odt=odt)
    objetivo_servicio = odt.servicio_editado if odt.servicio_editado is not None else odt.servicio
    objetivo_monto = odt.valor_pago_editado if odt.valor_pago_editado is not None else odt.valor_pago_tecnico
    cambia_objetivo = (creado or seguimiento.servicio_objetivo != objetivo_servicio or
                      seguimiento.monto_objetivo != objetivo_monto or
                      seguimiento.corrige_servicio != (odt.servicio_editado is not None) or
                      seguimiento.corrige_monto != (odt.valor_pago_editado is not None))
    if not cambia_objetivo:
        return seguimiento
    anterior = seguimiento.estado if not creado else ""
    seguimiento.servicio_objetivo = objetivo_servicio
    seguimiento.monto_objetivo = objetivo_monto
    seguimiento.corrige_servicio = odt.servicio_editado is not None
    seguimiento.corrige_monto = odt.valor_pago_editado is not None
    seguimiento.estado = "ACTUALIZADA" if coinciden(odt, seguimiento) else "PENDIENTE"
    seguimiento.actualizada_en = timezone.now() if seguimiento.estado == "ACTUALIZADA" else None
    seguimiento.save()
    EventoCorreccionODT.objects.create(odt=odt, estado_anterior=anterior,
        estado_nuevo=seguimiento.estado, usuario=usuario,
        detalle="Nuevo objetivo de corrección guardado en SSTT")
    return seguimiento


_NO_CARGADO = object()


def verificar_sincronizacion(odt, *, seguimiento=_NO_CARGADO):
    """Comparar con SoftGuard luego de actualizar sus valores originales."""
    if seguimiento is _NO_CARGADO:
        seguimiento = CorreccionODT.objects.select_for_update().filter(odt=odt).first()
    if not seguimiento:
        return
    coincide = coinciden(odt, seguimiento)
    nuevo_estado = "ACTUALIZADA" if coincide else (
        "PENDIENTE" if seguimiento.estado == "ACTUALIZADA" else seguimiento.estado)
    if nuevo_estado == seguimiento.estado:
        return
    anterior = seguimiento.estado
    seguimiento.estado = nuevo_estado
    seguimiento.actualizada_en = timezone.now() if coincide else None
    seguimiento.save(update_fields=["estado", "actualizada_en"])
    EventoCorreccionODT.objects.create(odt=odt, estado_anterior=anterior,
        estado_nuevo=nuevo_estado, detalle="Verificación automática tras sincronización SoftGuard")
