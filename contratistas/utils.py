import re
import unicodedata


def normalizar_nombre(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto.strip()).upper()


def buscar_contratista_por_tecnico(nombre):
    """Coincidencia exacta normalizada, nunca aproximada, para evitar pagos erróneos."""
    from .models import EquivalenciaSoftGuard
    clave = normalizar_nombre(nombre)
    if not clave:
        return None
    equivalencia = EquivalenciaSoftGuard.objects.select_related("contratista").filter(
        clave_normalizada=clave, contratista__activo=True
    ).first()
    return equivalencia.contratista if equivalencia else None
