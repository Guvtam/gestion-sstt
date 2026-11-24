"""Proyección de texto técnico: omite fragmentos administrativos identificables."""
import re

ADMINISTRATIVO = re.compile(
    r"\$|\b(?:CLP|USD|pesos|d[oó]lares|monto\w*|costo\w*|precio\w*|tarifa\w*|importe\w*|valor\w*|saldo\w*|boleta\w*|total|"
    r"factur\w*|pago\w*|requisici[oó]n|banco\w*|honorario\w*|cuenta bancaria|"
    r"transferencia\w*)\b|\b\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?\b", re.I)


def texto_tecnico(texto):
    partes = re.split(r"\n+|(?<=[.!?;])\s+", str(texto or ""))
    return "\n".join("[Contenido administrativo omitido]" if ADMINISTRATIVO.search(p) else p
                     for p in partes if p.strip())
