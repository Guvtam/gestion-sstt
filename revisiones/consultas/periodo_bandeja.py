"""Fechas iniciales de pagos; reutiliza la selección facturable, sin modificarla."""
from datetime import timedelta
from ..acceso_instalacion import SERVICIO_INSTALACION, limitar_pagos
from ..dominio.facturacion import SeleccionFacturacion
from ..dominio.servicios import SERVICIOS_PRINCIPALES
from ..facturacion_models import FacturacionODT
from .facturacion import odts_facturables


def periodo_inicial(usuario, hoy, *, instalacion=False):
    anterior = hoy.replace(day=1) - timedelta(days=1)
    desde, hasta = anterior.replace(day=21), hoy.replace(day=20)
    # No adelantar un período que todavía no termina, ni producir desde > hasta.
    if hoy <= hasta:
        return desde, hasta
    servicios = (SERVICIO_INSTALACION,) if instalacion else SERVICIOS_PRINCIPALES
    seleccion = SeleccionFacturacion(desde, hasta, servicios=servicios)
    if odts_facturables(seleccion, usuario=usuario).filter(item_facturacion__isnull=True).exists():
        return desde, hasta
    evidencia = limitar_pagos(usuario, FacturacionODT.objects.filter(
        facturacion__periodo__fecha_desde=desde, facturacion__periodo__fecha_hasta=hasta), historico=True)
    if not instalacion:
        evidencia = evidencia.filter(servicio_facturado__in=servicios)
    else:
        from ..acceso_instalacion import limitar_instalacion
        evidencia = limitar_instalacion(evidencia, historico=True)
    # Una cabecera vacía o un período sin atenciones no equivale a facturación completa.
    if evidencia.exists():
        return hoy.replace(day=21), hoy
    return desde, hasta
