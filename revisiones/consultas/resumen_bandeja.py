"""Resumen visual, sin modificar reglas de pago ni clasificación de cuentas."""
from decimal import Decimal
import re
from django.db.models import Count, Sum, Case, When, BooleanField, Value
from .pagos import importe_efectivo, condicion_aprobada
from .servicios import servicio_normalizado
from ..dominio.servicios import categoria_servicio, normalizar_servicio

CATEGORIAS = (
    ("correctiva_con_cobro", "Correctiva con cobro"),
    ("correctiva_sin_cobro", "Correctiva sin cobro"),
    ("preventivo", "Preventivos"), ("renovacion", "Renovaciones"),
    ("acuerdo_comercial", "Acuerdo comercial"), ("presupuesto", "Presupuesto"),
    ("nueva_instalacion", "Nueva instalación"),
    ("nueva_instalacion_cruzverde", "Nueva instalación Cruzverde"),
    ("otros", "Otros servicios / sin servicio"),
)
MANTENIMIENTO = {"correctiva_con_cobro", "correctiva_sin_cobro", "preventivo",
                 "renovacion", "acuerdo_comercial", "presupuesto"}


def indicador(nombre):
    return {"nombre": nombre, "cantidad": 0, "monto": Decimal("0")}


def resumen_bandeja(registros):
    tipos = {t: indicador(t) for t in ("B2B", "B2C", "Sin clasificar")}
    marcas = {m: indicador(m) for m in ("Cruz Verde", "Tattersall", "Enel")}
    servicios = {c: indicador(n) for c, n in CATEGORIAS}
    mantenimiento = indicador("Mantenimiento aprobado")
    instalaciones = indicador("Instalaciones B2C aprobadas")
    otros_aprobados = indicador("Otros servicios aprobados")
    total = indicador("Total del período filtrado")
    grupos = registros.order_by().annotate(
        _servicio_resumen=servicio_normalizado(),
        _aprobada_resumen=Case(When(condicion_aprobada(), then=Value(True)),
                              default=Value(False), output_field=BooleanField()),
    ).values("tipo_cliente", "cuenta_completa", "_servicio_resumen", "_aprobada_resumen").annotate(
        cantidad=Count("pk"), monto=Sum(importe_efectivo()))
    for fila in grupos:
        cantidad, monto = fila["cantidad"], fila["monto"] or Decimal("0")
        tipo = fila["tipo_cliente"] if fila["tipo_cliente"] in ("B2B", "B2C") else "Sin clasificar"
        servicio = fila["_servicio_resumen"]
        categoria = ("nueva_instalacion" if normalizar_servicio(servicio) ==
                     "MANTENIMIENTO NUEVA INSTALACION" else categoria_servicio(servicio))
        destinos = [total, tipos[tipo], servicios[categoria]]
        nombre = re.sub(r"[^A-Z0-9]+", " ", normalizar_servicio(fila["cuenta_completa"]))
        # Desglose por nombre visible; no reasigna tipo de cliente ni CECO.
        if re.search(r"\bCRUZ\s*VERDE\b", nombre): destinos.append(marcas["Cruz Verde"])
        elif re.search(r"\bTATTERSALL\b", nombre): destinos.append(marcas["Tattersall"])
        elif re.search(r"\bENEL\b", nombre): destinos.append(marcas["Enel"])
        if fila["_aprobada_resumen"]:
            if categoria in MANTENIMIENTO: destinos.append(mantenimiento)
            elif categoria == "nueva_instalacion" and tipo == "B2C": destinos.append(instalaciones)
            else: destinos.append(otros_aprobados)
        for destino in destinos:
            destino["cantidad"] += cantidad
            destino["monto"] += monto
    return {"tipos": [v for k,v in tipos.items() if k != "Sin clasificar" or v["cantidad"]],
            "marcas": list(marcas.values()),
            "servicios": [v for k,v in servicios.items() if k != "otros" or v["cantidad"]],
            "mantenimiento": mantenimiento, "instalaciones": instalaciones,
            "otros_aprobados": otros_aprobados, "total": total}
