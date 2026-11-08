"""Lecturas para reportes; el adaptador debe autorizar antes de invocarlas."""
from django.db.models import Q
from ..models import ODT
from ..facturacion_models import FacturacionODT
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


def items_facturados(periodo, seleccion=None):
    consulta = FacturacionODT.objects.filter(facturacion__periodo=periodo)
    if seleccion is not None:
        consulta = consulta.filter(facturacion_id__in=seleccion)
    return list(consulta.select_related("odt", "facturacion").order_by(
        "facturacion__contratista", "odt__numero"))


def odts_aprobadas(contratista, desde, hasta, *, estado="", tipo_cliente="", servicios=(), q=""):
    registros = ODT.objects.select_related("revision").filter(
        condicion_aprobada(), contratista=contratista,
        fecha_finalizacion__date__gte=desde, fecha_finalizacion__date__lte=hasta,
    ).order_by("fecha_finalizacion", "numero")
    if estado:
        registros = registros.filter(estado_softguard=estado)
    if tipo_cliente:
        registros = registros.filter(tipo_cliente=tipo_cliente)
    if servicios:
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
    return list(registros)
