"""Preferencia visual personal; no concede permisos ni modifica observaciones."""
from django.db.models import BooleanField, Case, CharField, F, Q, Value, When
from django.db.models.functions import Cast
from ..acceso_instalacion import normalizado


def marcar_fallos(registros, usuario):
    activo = usuario.get_username().strip().casefold() == "jiturriaga"
    if not activo:
        return registros.annotate(es_fallo_prueba=Value(False,output_field=BooleanField())), False
    registros=registros.alias(_observacion_fdp=normalizado(Cast(F("observaciones_insumos"), CharField())))
    condicion=(Q(_observacion_fdp__contains="FDP") |
        Q(_observacion_fdp__regex=r"FALL[OA]S?\s+DE\s+PRUEBA") |
        Q(_observacion_fdp__regex=r"FALL[OA]S?\s+DE\s+COMUNICACION"))
    return registros.annotate(es_fallo_prueba=Case(When(condicion,then=Value(True)),
        default=Value(False),output_field=BooleanField())), True
