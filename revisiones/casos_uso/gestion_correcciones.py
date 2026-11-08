"""Cambio de gestión y su evento en una misma transacción."""
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone
from .autorizacion import exigir_permiso, exigir_alcance_coordinador
from ..acceso_coordinadores import es_coordinador_sstt
from ..correcciones import coinciden, registrar_cambio_manual
from ..dominio.errores import ODTBloqueada, ODTNoEncontrada, VerificacionCoordinadorFallida
from ..dominio.gestion_correcciones import CorreccionGestionada, estado_gestion
from ..dominio.validacion_odt import numero_odt
from ..models import ODT, CorreccionODT, EventoCorreccionODT


def gestionar_correccion(usuario, *, numero, estado, verificar_alcance=None):
    if not usuario.is_authenticated or not usuario.is_active:
        raise PermissionDenied
    coordinador = es_coordinador_sstt(usuario)
    if not coordinador:
        exigir_permiso(usuario, "revisiones.editar_odt_sstt")
    numero = numero_odt(numero, formateado=True)
    if coordinador:
        if verificar_alcance is None:
            exigir_alcance_coordinador(usuario, numero)
        else:
            try:
                permitido = verificar_alcance(numero)
                if not isinstance(permitido, bool):
                    raise ValueError("Verificación de alcance inválida")
            except Exception:
                raise VerificacionCoordinadorFallida("No se pudo verificar el coordinador en SQL.") from None
            if not permitido:
                raise PermissionDenied
    estado = estado_gestion(estado, coordinador=coordinador)
    with transaction.atomic():
        try:
            odt = ODT.objects.select_for_update().get(numero=numero)
        except ODT.DoesNotExist:
            raise ODTNoEncontrada from None
        seguimiento = CorreccionODT.objects.select_for_update().filter(odt=odt).first()
        if seguimiento is None:
            if odt.servicio_editado is None and odt.valor_pago_editado is None:
                raise ODTBloqueada("La ODT no tiene modificaciones.")
            seguimiento = registrar_cambio_manual(odt, usuario)
        if seguimiento.estado == "ACTUALIZADA" or coinciden(odt, seguimiento):
            raise ODTBloqueada("La ODT ya coincide con SoftGuard. Actualiza la pantalla.")
        cambio = seguimiento.estado != estado
        if cambio:
            anterior = seguimiento.estado
            seguimiento.estado = estado
            seguimiento.actualizado_por = usuario
            seguimiento.gestionado_en = timezone.now()
            seguimiento.save(update_fields=["estado", "actualizado_por", "gestionado_en"])
            EventoCorreccionODT.objects.create(
                odt=odt, estado_anterior=anterior, estado_nuevo=estado, usuario=usuario,
                detalle="Cambio manual del estado de gestión",
            )
        return CorreccionGestionada(estado, cambio)
