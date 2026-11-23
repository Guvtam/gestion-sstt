"""Auditoría y reparación del espejo operativo técnico/contratista."""
from django.db import transaction
from ..dominio.contratistas_odt import contratista_desde_tecnico
from ..dominio.pagos import estado_pago_efectivo
from ..models import ODT, Revision, EventoRevision

PREFIJO_AUDITORIA = '[CONTRATISTA]'


def registrar_cambios_contratista(cambios, origen):
    if not cambios:
        return
    estados = dict(Revision.objects.filter(odt_id__in=[o.pk for o, _, _ in cambios])
                   .values_list('odt_id', 'estado'))
    EventoRevision.objects.bulk_create([
        EventoRevision(odt=odt, estado_anterior=estado_pago_efectivo(estados.get(odt.pk)),
            estado_nuevo=estado_pago_efectivo(estados.get(odt.pk)),
            comentario=f'{PREFIJO_AUDITORIA} {anterior or "Sin contratista"} → {nuevo}. {origen}')
        for odt, anterior, nuevo in cambios
    ], batch_size=250)


def reparar_lote_contratistas(ids, *, aplicar=False):
    """El llamador debe tomar el bloqueo compartido con la sincronización."""
    def preparar(registros):
        cambios = []
        for odt in registros:
            nuevo = contratista_desde_tecnico(odt.tecnico, odt.contratista)
            if nuevo != odt.contratista:
                cambios.append((odt, odt.contratista, nuevo))
        return cambios
    consulta = ODT.objects.filter(pk__in=ids).order_by('pk')
    if not aplicar:
        return [(o.numero, antes, nuevo) for o, antes, nuevo in preparar(consulta)]
    with transaction.atomic():
        cambios = preparar(consulta.select_for_update())
        for odt, _, nuevo in cambios:
            odt.contratista = nuevo
        if cambios:
            ODT.objects.bulk_update([o for o, _, _ in cambios], ['contratista'], batch_size=250)
            registrar_cambios_contratista(cambios, 'Reparación desde el técnico de la última sincronización local.')
        return [(o.numero, antes, nuevo) for o, antes, nuevo in cambios]
