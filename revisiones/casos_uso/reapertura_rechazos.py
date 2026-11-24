"""Reapertura explícita de un rechazo; la edición normal conserva sus bloqueos."""
from django.db import transaction
from .autorizacion import exigir_permiso_operativo
from .edicion_odt import ResultadoRevision
from ..acceso_instalacion import exigir_odt_pago
from ..dominio.errores import DatosODTInvalidos, ODTBloqueada, ODTNoEncontrada
from ..dominio.validacion_odt import numero_odt, texto
from ..facturacion_models import FacturacionODT
from ..models import ODT, Revision, EventoRevision


def deshacer_rechazo(usuario, *, numero, motivo):
    exigir_permiso_operativo(usuario, 'revisiones.revisar_pago_sstt')
    numero = numero_odt(numero, formateado=True)
    motivo = texto(motivo)
    if not motivo:
        raise DatosODTInvalidos('Debes indicar el motivo para deshacer el rechazo.')
    with transaction.atomic():
        odt = ODT.objects.select_for_update().filter(numero=numero).first()
        if odt is None:
            raise ODTNoEncontrada('ODT no encontrada.')
        exigir_odt_pago(usuario, odt)
        revision = Revision.objects.select_for_update().filter(odt=odt).first()
        if FacturacionODT.objects.filter(odt=odt).exists():
            raise ODTBloqueada('La ODT ya está facturada y no permite deshacer el rechazo.')
        if revision is None or revision.estado != 'RECHAZADA':
            raise ODTBloqueada('La ODT ya no está rechazada. Actualiza la pantalla.')
        motivo_anterior = revision.observacion
        revision.estado = 'APROBADA'
        revision.observacion = motivo
        revision.actualizado_por = usuario
        revision.save(update_fields=['estado', 'observacion', 'actualizado_por', 'actualizado_en'])
        EventoRevision.objects.create(odt=odt, estado_anterior='RECHAZADA', estado_nuevo='APROBADA',
            usuario=usuario, comentario='[REAPERTURA] Rechazo deshecho y ODT aprobada. Motivo: '+motivo
                + (' | Motivo del rechazo anterior: '+motivo_anterior if motivo_anterior else ''))
        return ResultadoRevision('APROBADA', True)
