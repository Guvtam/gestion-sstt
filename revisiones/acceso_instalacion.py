"""Alcance adicional de pagos: nueva instalación, excluyendo Cruzverde."""
from django.core.exceptions import PermissionDenied
from django.db.models import F, Value
from django.db.models.functions import Replace, Trim, Upper

SERVICIO_INSTALACION = 'MANTENIMIENTO NUEVA INSTALACION'
PERMISO_INSTALACION = 'revisiones.gestionar_pagos_nueva_instalacion'


def pagos_instalacion(usuario):
    return (usuario.is_authenticated and usuario.is_active and not usuario.is_superuser
            and usuario.has_perm(PERMISO_INSTALACION))


def normalizado(expresion):
    for origen, destino in zip('áéíóúÁÉÍÓÚ', 'aeiouAEIOU'):
        expresion = Replace(expresion, Value(origen), Value(destino))
    return Upper(Trim(expresion))


def limitar_instalacion(registros, *, historico=False):
    from .consultas.servicios import servicio_normalizado
    expresion = normalizado(F('servicio_facturado')) if historico else servicio_normalizado()
    return registros.alias(servicio_autorizado_instalacion=expresion).filter(
        servicio_autorizado_instalacion=SERVICIO_INSTALACION)


def limitar_pagos(usuario, registros, *, historico=False):
    return limitar_instalacion(registros, historico=historico) if pagos_instalacion(usuario) else registros


def es_odt_instalacion(usuario, numero):
    from .models import ODT
    return pagos_instalacion(usuario) and limitar_instalacion(ODT.objects.filter(numero=numero)).exists()


def exigir_odt_pago(usuario, odt, servicio_nuevo=None):
    if not pagos_instalacion(usuario):
        return
    from .dominio.servicios import normalizar_servicio, servicio_efectivo
    actual = servicio_efectivo(odt.servicio, odt.servicio_editado)
    if (normalizar_servicio(actual) != SERVICIO_INSTALACION
            or servicio_nuevo is not None and normalizar_servicio(servicio_nuevo) != SERVICIO_INSTALACION):
        raise PermissionDenied('Solo puedes gestionar pagos de Mantenimiento nueva instalación.')


def exigir_factura_completa(usuario, factura):
    """Una requisición es compartida por contratista/período; no editar mezclas."""
    if not pagos_instalacion(usuario):
        return
    from .facturacion_models import FacturacionODT
    todos = FacturacionODT.objects.filter(facturacion=factura)
    permitidos = limitar_instalacion(todos, historico=True)
    if not permitidos.exists() or todos.exclude(pk__in=permitidos.values('pk')).exists():
        raise PermissionDenied('Esta requisición incluye otros servicios; debe gestionarla supervisión.')
