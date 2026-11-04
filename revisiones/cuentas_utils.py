
import re


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
