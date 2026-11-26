"""Lecturas para reportes; el adaptador debe autorizar antes de invocarlas."""
from django.db.models import Q
from ..models import ODT
from ..facturacion_models import FacturacionODT
from .montos_bandeja import filtrar_montos
from .pagos import condicion_aprobada

def datos_contratista_pdf(nombre):
    from contratistas.models import Contratista, EquivalenciaSoftGuard
    from contratistas.utils import normalizar_nombre
    clave = normalizar_nombre(nombre)
    equivalencia = EquivalenciaSoftGuard.objects.select_related("contratista").filter(
        clave_normalizada=clave
    ).first()
    if equivalencia:
        return equivalencia.contratista
    candidatos = [c for c in Contratista.objects.all()
                  if clave and clave in {normalizar_nombre(c.nombre), normalizar_nombre(c.nombre_softguard)}]
    return candidatos[0] if len(candidatos) == 1 else None


def items_facturados(periodo, seleccion=None, usuario=None):
    consulta = FacturacionODT.objects.filter(facturacion__periodo=periodo)
    if seleccion is not None:
        consulta = consulta.filter(facturacion_id__in=seleccion)
    from ..acceso_instalacion import limitar_pagos
    if usuario is not None:
        consulta = limitar_pagos(usuario, consulta, historico=True)
    return list(consulta.select_related("odt", "facturacion").order_by(
        "facturacion__contratista", "facturacion_id", "odt__numero"))


def odts_aprobadas(contratista, desde, hasta, *, estado="", tipo_cliente="", servicios=(), q="", montos=(), montos_filtrados=False, usuario=None):
    registros = ODT.objects.select_related("revision").filter(
        condicion_aprobada(), contratista=contratista,
        fecha_finalizacion__date__gte=desde, fecha_finalizacion__date__lte=hasta,
    ).order_by("fecha_finalizacion", "numero")
    if estado:
        registros = registros.filter(estado_softguard=estado)
    if tipo_cliente:
        registros = registros.filter(tipo_cliente=tipo_cliente)
    from ..acceso_instalacion import pagos_instalacion
    restringida = usuario is not None and pagos_instalacion(usuario)
    if restringida and servicios:
        from ..acceso_instalacion import SERVICIO_INSTALACION
        from ..dominio.servicios import normalizar_servicio
        if any(normalizar_servicio(s) != SERVICIO_INSTALACION for s in servicios):
            return []
    if servicios and not restringida:
        registros = registros.filter(
            Q(servicio_editado__isnull=True, servicio__in=servicios)
            | Q(servicio_editado__in=servicios))
    if q:
        filtro = (Q(contratista__icontains=q) | Q(tecnico__icontains=q)
                  | Q(cuenta_completa__icontains=q) | Q(servicio__icontains=q)
                  | Q(servicio_editado__icontains=q) | Q(direccion__icontains=q))
        if q.isdigit():
            filtro |= Q(numero=int(q))
        registros = registros.filter(filtro)
    from ..acceso_instalacion import limitar_pagos
    if usuario is not None:
        registros = limitar_pagos(usuario, registros)
    return list(filtrar_montos(registros, montos, montos_filtrados))
