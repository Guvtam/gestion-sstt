"""Período y selección de facturación independientes de HTTP."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta


class FacturacionInvalida(ValueError):
    pass


class FacturacionNoEncontrada(LookupError):
    pass


def validar_periodo(desde, hasta):
    if (not isinstance(desde, date) or isinstance(desde, datetime)
            or not isinstance(hasta, date) or isinstance(hasta, datetime)):
        raise FacturacionInvalida("Debes indicar ambas fechas válidas.")
    try:
        siguiente = (desde.replace(day=28) + timedelta(days=4)).replace(day=1)
    except (ValueError, OverflowError):
        raise FacturacionInvalida("Debes indicar ambas fechas válidas.") from None
    if desde.day != 21 or hasta != siguiente.replace(day=20):
        raise FacturacionInvalida("El período debe comenzar el día 21 y terminar el día 20 del mes siguiente.")


@dataclass(frozen=True)
class SeleccionFacturacion:
    desde: date
    hasta: date
    contratistas: tuple = ()
    servicios: tuple = ()
    contratistas_filtrados: bool = False
    tipo_cliente: str = ""
    estado: str = ""
    q: str = ""

    def __post_init__(self):
        validar_periodo(self.desde, self.hasta)
        for nombre in ("contratistas", "servicios"):
            valores = getattr(self, nombre)
            if isinstance(valores, (str, bytes)):
                raise FacturacionInvalida("Selección de filtros inválida.")
            object.__setattr__(self, nombre, tuple(sorted({str(v) for v in valores if v})))
        for nombre in ("tipo_cliente", "estado", "q"):
            object.__setattr__(self, nombre, str(getattr(self, nombre) or "").strip())

    def clave(self):
        return {
            "desde": self.desde.isoformat(), "hasta": self.hasta.isoformat(),
            "contratistas": list(self.contratistas), "servicios": list(self.servicios),
            "contratistas_filtrados": bool(self.contratistas_filtrados),
            "tipo_cliente": self.tipo_cliente, "estado": self.estado, "q": self.q,
        }
