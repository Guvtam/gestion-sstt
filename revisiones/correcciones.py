from django.utils import timezone
from .models import CorreccionODT, EventoCorreccionODT
from .dominio.conciliacion_correcciones import MARCA_MONTO, servicio_confirmado, monto_confirmado


def coinciden(odt, seguimiento):
    return (servicio_confirmado(odt.servicio, seguimiento.servicio_objetivo, seguimiento.corrige_servicio)
            and monto_confirmado(odt.valor_pago_tecnico, seguimiento.monto_objetivo, seguimiento.corrige_monto))


def retirar_marca_monto(odt, seguimiento):
    """Retira solo la marca confirmada; el objetivo $2 persiste para auditoría."""
    if (seguimiento.corrige_monto and seguimiento.monto_objetivo == MARCA_MONTO
            and odt.valor_pago_editado == MARCA_MONTO and coinciden(odt, seguimiento)):
        odt.valor_pago_editado = None
        odt.modificado_manualmente = odt.servicio_editado is not None
        odt.save(update_fields=["valor_pago_editado", "modificado_manualmente"])
        return True
    return False


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
    retirada = retirar_marca_monto(odt, seguimiento) if seguimiento.estado == "ACTUALIZADA" else False
    EventoCorreccionODT.objects.create(odt=odt, estado_anterior=anterior,
        estado_nuevo=seguimiento.estado, usuario=usuario,
        detalle=(f"Nuevo objetivo de corrección guardado en SSTT. Servicio: {seguimiento.servicio_objetivo}; "
                 f"monto solicitado: ${seguimiento.monto_objetivo}."
                 + (f" Marca $2 retirada; monto real SoftGuard: ${odt.valor_pago_tecnico}." if retirada else "")))
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
    retirada = retirar_marca_monto(odt, seguimiento) if coincide else False
    if nuevo_estado == seguimiento.estado and not retirada:
        return
    anterior = seguimiento.estado
    seguimiento.estado = nuevo_estado
    seguimiento.actualizada_en = timezone.now() if coincide else None
    seguimiento.save(update_fields=["estado", "actualizada_en"])
    EventoCorreccionODT.objects.create(odt=odt, estado_anterior=anterior,
        estado_nuevo=nuevo_estado, detalle=("Verificación automática tras sincronización SoftGuard"
            + (f". Marca $2 retirada; monto real SoftGuard: ${odt.valor_pago_tecnico}; solicitud original conservada." if retirada else "")))
