"""Identidad y clasificación de cuenta; reglas sin acceso a base de datos."""

import re


TIPO_CLIENTE_PREDETERMINADO = "B2C"


def normalizar_codigo_cuenta(cuenta_completa):
    """
    Extrae y normaliza códigos de cuenta SoftGuard.

    Ejemplos:
    FIR-5429 - ABASTIBLE -> FIR-5429
    FIR-C489 - CRUZ VERDE -> FIR-C489
    FIR-231C - CRUZ VERDE -> FIR-231C
    FIR-B001 - PARQUE DEL MAR -> FIR-B001
    FIR - 5429 -> FIR-5429
    """

    if not cuenta_completa:
        return ""

    texto = str(cuenta_completa).strip().upper()

    coincidencia = re.match(
        r"^([A-Z0-9]+)\s*-\s*([A-Z0-9]+)(?=\s+-\s+|$)",
        texto
    )

    if not coincidencia:
        return ""

    linea, numero = coincidencia.groups()

    return f"{linea}-{numero}"


def normalizar_tipo_cliente(valor):
    tipo = str(valor or "").strip().upper()
    return tipo if tipo in ("B2B", "B2C") else "SIN_CLASIFICAR"


def tipo_cliente_cuenta(cuenta_completa, catalogo):
    """B2C por defecto para cuentas válidas sin clasificación en catálogo."""
    codigo = normalizar_codigo_cuenta(cuenta_completa)
    if not codigo:
        return "SIN_CLASIFICAR"
    cuenta = catalogo.get(codigo)
    tipo = normalizar_tipo_cliente(cuenta.tipo_cliente if cuenta else None)
    return tipo if tipo in ("B2B", "B2C") else TIPO_CLIENTE_PREDETERMINADO
