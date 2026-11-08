"""Lectura de filtros: sin HTTP, base de datos ni decisiones de autorización."""
from dataclasses import dataclass
from datetime import date, timedelta
from .servicios import SERVICIOS_PRINCIPALES

SIN_TECNICO_FILTRO = "__SIN_TECNICO__"


@dataclass(frozen=True)
class SeleccionBandeja:
    valores: tuple[tuple[str, str], ...]
    servicios: tuple[str, ...]
    contratistas: tuple[str, ...]
    contratistas_explicitos: bool
    numero_exacto: str | None

    def filtros(self) -> dict[str, str]:
        return dict(self.valores)


def leer_seleccion(parametros, *, por_creacion: bool, hoy: date) -> SeleccionBandeja:
    """Distingue parámetro ausente, valor vacío y selección explícitamente vacía."""
    filtros = {k: parametros.get(k, "").strip() for k in (
        "estado", "revision", "coordinador", "q", "fecha_desde", "fecha_hasta",
    )}
    if "estado" not in parametros:
        filtros["estado"] = "" if por_creacion else "Finalizado"
    if "fecha_desde" not in parametros:
        anterior = hoy.replace(day=1) - timedelta(days=1)
        filtros["fecha_desde"] = anterior.replace(day=21).isoformat()
    if "fecha_hasta" not in parametros:
        filtros["fecha_hasta"] = hoy.isoformat()
    servicios = tuple(parametros.getlist("servicios"))
    if not parametros and not por_creacion:
        servicios = tuple(SERVICIOS_PRINCIPALES)
    return SeleccionBandeja(
        valores=tuple(filtros.items()), servicios=servicios,
        contratistas=tuple(parametros.getlist("contratista")),
        contratistas_explicitos="contratistas_filtrados" in parametros or "contratista" in parametros,
        numero_exacto=parametros.get("numero_odt", "").strip() if "numero_odt" in parametros else None,
    )
