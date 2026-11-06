"""Contrato de campos originales del DW; nunca incluye ediciones o facturación."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.utils import timezone


class RegistroOrigenInvalido(ValueError):
    pass


def texto(valor, maximo=None):
    valor = str(valor).strip() if valor is not None else ""
    return valor[:maximo] if maximo else valor


def fecha_valida(valor):
    if valor is None:
        return None
    if not isinstance(valor, date):
        raise RegistroOrigenInvalido("Fecha de origen inválida")
    if valor.year <= 1900:
        return None
    if isinstance(valor, datetime) and timezone.is_naive(valor):
        return timezone.make_aware(valor, timezone.get_default_timezone())
    return valor


def fecha_hora(valor):
    valor = fecha_valida(valor)
    if valor is not None and not isinstance(valor, datetime):
        raise RegistroOrigenInvalido("Se esperaba fecha con hora")
    return valor


def decimal_valido(valor):
    try:
        numero = Decimal(str(valor)) if valor is not None else Decimal("0")
        return numero if numero.is_finite() else Decimal("0")
    except (InvalidOperation, ValueError):
        return Decimal("0")


def transformar_registro(registro):
    try:
        valor = Decimal(str(registro.get("Numero")))
        if not valor.is_finite() or valor != valor.to_integral_value() or not 0 < valor <= 2147483647:
            raise RegistroOrigenInvalido("Número de ODT inválido")
        numero = int(valor)
    except (InvalidOperation, ValueError, TypeError, AttributeError):
        raise RegistroOrigenInvalido("Número de ODT inválido") from None
    campos_texto = {
        "codigo_tecnico": ("CodigoTecnico", 20), "tecnico": ("Tecnico", 200),
        "cuenta_completa": ("CuentaCompleta", None), "direccion": ("Direccion", 300),
        "provincia": ("Provincia", 150), "localidad": ("Localidad", 150),
        "tipo_servicio": ("TipoServicio", 30), "servicio": ("Servicio", 150),
        "descripcion_servicio": ("Servicio", None),
        "observaciones_insumos": ("ObservacionesInsumos", None),
        "estado_softguard": ("Estado", 50), "usuario_creador": ("UsuarioCreador", 200),
        "correo_creador": ("CorreoCreador", 254),
    }
    datos = {destino: texto(registro.get(origen), limite)
             for destino, (origen, limite) in campos_texto.items()}
    for destino, origen in (
        ("fecha_creacion", "FechaCreacion"), ("fecha_modificacion", "FechaModificacion"),
        ("fecha_finalizacion", "FechaFinalizacion"), ("fecha_pago", "FechaPago"),
    ):
        datos[destino] = fecha_hora(registro.get(origen))
    visita = fecha_valida(registro.get("FechaVisita"))
    datos["fecha_visita"] = visita.date() if isinstance(visita, datetime) else visita
    for destino, origen in (
        ("monto_origen", "Valor"), ("costo_mano_obra", "CostoManoObra"),
        ("valor_pago_tecnico", "ValorPagoTecnico"), ("tiempo_trabajo_hrs", "TiempoTrabajoHrs"),
    ):
        datos[destino] = decimal_valido(registro.get(origen))
    return numero, datos
