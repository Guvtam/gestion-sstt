"""Proyección renovable del origen: nunca sustituye asignaciones manuales."""
import hashlib
import json
from datetime import timedelta

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime


def firma_catalogo(catalogo):
    return hashlib.sha256(json.dumps(catalogo, sort_keys=True).encode()).hexdigest()


def resultado_local(resultado, firma, verificado, catalogo):
    horas = float(getattr(settings, "SSTT_COORDINADORES_VIGENCIA_HORAS", 6))
    ahora = timezone.now()
    if (not verificado or not firma or firma != firma_catalogo(catalogo)
            or horas <= 0 or not ahora - timedelta(hours=horas) <= verificado <= ahora):
        return None
    if not isinstance(resultado, dict) or not isinstance(resultado.get("identificado"), bool):
        return None
    resultado = dict(resultado)
    if resultado["identificado"]:
        datos = catalogo.get(resultado.get("id_softguard"))
        if datos is None or datos["usuario"] != resultado.get("usuario"):
            return None
        resultado["nombre"] = datos["nombre"]
    for campo in ("fecha_alta", "fecha_ultima_accion"):
        if isinstance(resultado.get(campo), str):
            resultado[campo] = parse_datetime(resultado[campo])
    return resultado


def actualizar_proyeccion(*, tamano_lote=250, simular=False):
    from ..coordinadores_softguard import catalogo_coordinadores
    from ..dominio.coordinadores import inferir_coordinador
    from ..models import ODT, ProyeccionCoordinadorODT
    from ..servicios_sql import consultar_eventos_coordinadores
    if not 1 <= tamano_lote <= 250:
        raise ValueError("El lote debe estar entre 1 y 250.")
    catalogo = catalogo_coordinadores()
    firma = firma_catalogo(catalogo)
    lote, total = [], 0

    def guardar(filas):
        por_numero = {numero: [] for _, numero in filas}
        for evento in consultar_eventos_coordinadores(list(por_numero), catalogo):
            numero = int(evento["NumeroODT"])
            if numero in por_numero:
                por_numero[numero].append(evento)
        verificado = timezone.now()
        resultados = [(pk, inferir_coordinador(por_numero[numero], catalogo))
                      for pk, numero in filas]
        if not simular:
            with transaction.atomic():
                ProyeccionCoordinadorODT.objects.bulk_create([
                    ProyeccionCoordinadorODT(
                        odt_id=pk, resultado=json.loads(json.dumps(resultado, cls=DjangoJSONEncoder)),
                        firma_catalogo=firma, verificado_en=verificado,
                    ) for pk, resultado in resultados
                ], update_conflicts=True, unique_fields=["odt"],
                    update_fields=["resultado", "firma_catalogo", "verificado_en"], batch_size=250)


    for fila in ODT.objects.order_by("pk").values_list("pk", "numero").iterator(chunk_size=250):
        lote.append(fila)
        if len(lote) == tamano_lote:
            guardar(lote)
            total += len(lote)
            lote.clear()
    if lote:
        guardar(lote)
        total += len(lote)
    return total
