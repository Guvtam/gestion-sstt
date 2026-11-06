from .servicios_sql import consultar_historial_odt, consultar_eventos_coordinadores
from .dominio.coordinadores import inferir_coordinador
from .dominio.validacion_odt import numero_odt

COORDINADORES_SOFTGUARD = {
    4: {"nombre": "Josué Tapia", "usuario": "jtapia"},
    1256: {"nombre": "Jurguen Bicz", "usuario": "jbicz"},
    549: {"nombre": "Yasna Ramírez", "usuario": "yramirez"},
    1336: {"nombre": "Romina Silva", "usuario": "rsilva"},
}


def identificar_coordinador_softguard(numero):
    """Compatibilidad de consulta individual; la regla se comparte con los lotes."""
    return inferir_coordinador(consultar_historial_odt(numero), COORDINADORES_SOFTGUARD)


def puede_asignar_coordinador(user):
    return (user.is_authenticated and user.is_active
            and user.get_username().strip().casefold() in ("admin", "jiturriaga"))


def identificar_coordinador_odt(numero):
    """La asignación local persiste y se utiliza en todas las vistas y filtros."""
    from .models import AsignacionCoordinadorODT
    asignacion = AsignacionCoordinadorODT.objects.filter(odt__numero=numero).first()
    if asignacion is None:
        return identificar_coordinador_softguard(numero)
    return _datos_asignacion(asignacion.usuario_coordinador, asignacion.asignado_en)


def _datos_asignacion(usuario, asignado_en):
    datos = next((d for d in COORDINADORES_SOFTGUARD.values()
                  if d["usuario"] == usuario), None)
    if datos is None:
        raise ValueError("Coordinador asignado no reconocido.")
    return {
        "nombre": datos["nombre"], "usuario": datos["usuario"],
        "identificado": True, "asignacion_manual": True,
        "fecha_ultima_accion": asignado_en,
    }


class CoordinadoresNoDisponibles(Exception):
    def __init__(self, confirmados=None):
        super().__init__("No se pudo verificar el coordinador. Intenta nuevamente.")
        self.confirmados = dict(confirmados or {})


def identificar_coordinadores_odt(numeros):
    """Un lote: una consulta local y, si hace falta, una consulta al origen.

    Una falla no equivale a Sin identificar. Solo devuelve esa clasificación
    cuando la lectura terminó y no encontró un responsable inequívoco.
    """
    from .models import AsignacionCoordinadorODT
    numeros = list(dict.fromkeys(numero_odt(n) for n in numeros))
    if len(numeros) > 250:
        raise ValueError("El lote admite como máximo 250 ODT.")
    if not numeros:
        return {}
    resultados = {}
    try:
        for asignacion in AsignacionCoordinadorODT.objects.filter(odt__numero__in=numeros).values(
            "odt__numero", "usuario_coordinador", "asignado_en",
        ):
            resultados[asignacion["odt__numero"]] = _datos_asignacion(
                asignacion["usuario_coordinador"], asignacion["asignado_en"],
            )
        pendientes = [n for n in numeros if n not in resultados]
        if pendientes:
            movimientos = {n: [] for n in pendientes}
            for movimiento in consultar_eventos_coordinadores(pendientes, COORDINADORES_SOFTGUARD):
                numero = numero_odt(movimiento.get("NumeroODT"))
                if numero in movimientos:
                    movimientos[numero].append(movimiento)
            for numero, eventos in movimientos.items():
                resultados[numero] = inferir_coordinador(eventos, COORDINADORES_SOFTGUARD)
        return resultados
    except Exception:
        # No exponer errores del driver ni atribuir fallos a Sin identificar.
        raise CoordinadoresNoDisponibles(resultados) from None
