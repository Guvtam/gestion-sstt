"""Resumen sobre instantáneas facturadas, sin consultar valores operativos."""
from decimal import Decimal
from django.db.models import QuerySet

from ..cuentas_utils import cargar_catalogo_cuentas, tipo_cliente_cuenta
from ..dominio.servicios import categoria_servicio

NOMBRES_CATEGORIAS = {
    "correctiva_con_cobro": "Mantención correctiva con cobro",
    "correctiva_sin_cobro": "Mantención correctiva sin cobro",
    "renovacion": "Mantención renovación",
    "preventivo": "Mantenimiento preventivo",
    "acuerdo_comercial": "Mantenimiento acuerdo comercial",
    "presupuesto": "Mantenimiento presupuesto",
    "otros": "Otros servicios",
}


def resumir_items(items, catalogo=None):
    """Retorna todas las categorías aunque estén vacías.

    Monto y servicio son la instantánea de facturación; clasificación de cliente
    corresponde al catálogo actual, como en la regla vigente del historial.
    """
    if isinstance(items, QuerySet):
        if catalogo is None:
            catalogo = cargar_catalogo_cuentas(items.values_list("odt__cuenta_completa", flat=True))
        filas = items.iterator(chunk_size=1000)
    else:
        filas = list(items)
        if catalogo is None:
            catalogo = cargar_catalogo_cuentas(item.odt.cuenta_completa for item in filas)
    categorias = {
        clave: {"nombre": nombre, "monto": Decimal("0"), "cantidad": 0}
        for clave, nombre in NOMBRES_CATEGORIAS.items()
    }
    clientes = {
        clave: {"monto": Decimal("0"), "cantidad": 0, "promedio": Decimal("0")}
        for clave in ("B2B", "B2C", "SIN_CLASIFICAR")
    }
    total = Decimal("0")
    cantidad = 0
    for item in filas:
        monto = item.monto_facturado or Decimal("0")
        grupo = categorias[categoria_servicio(item.servicio_facturado)]
        grupo["monto"] += monto
        grupo["cantidad"] += 1
        cliente = clientes[tipo_cliente_cuenta(item.odt.cuenta_completa, catalogo)]
        cliente["monto"] += monto
        cliente["cantidad"] += 1
        total += monto
        cantidad += 1
    for cliente in clientes.values():
        if cliente["cantidad"]:
            cliente["promedio"] = cliente["monto"] / cliente["cantidad"]
    return {"categorias": categorias, "clientes": clientes, "total": total, "cantidad": cantidad}
