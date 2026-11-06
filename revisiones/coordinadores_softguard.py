from .servicios_sql import consultar_historial_odt, consultar_eventos_coordinadores
from .dominio.coordinadores import inferir_coordinador
from .dominio.validacion_odt import numero_odt

COORDINADORES_SOFTGUARD = {
    4: {"nombre": "Josué Tapia", "usuario": "jtapia"},
    1256: {"nombre": "Jurguen Bicz", "usuario": "jbicz"},
    549: {"nombre": "Yasna Ramírez", "usuario": "yramirez"},
    1336: {"nombre": "Romina Silva", "usuario": "rsilva"},
}


def catalogo_coordinadores():
    """El catálogo administrable prevalece sobre las cuatro identidades históricas."""
    from .models import ResponsableSoftGuard
    catalogo = {k: dict(v) for k, v in COORDINADORES_SOFTGUARD.items()}
    for responsable in ResponsableSoftGuard.objects.order_by("pk"):
        # Evita atribuir el mismo usuario a dos IDs al reemplazar una identidad.
        catalogo = {k: v for k, v in catalogo.items()
                    if k != responsable.id_softguard and v["usuario"] != responsable.usuario_softguard}
        if responsable.activo:
            catalogo[responsable.id_softguard] = {
                "nombre": responsable.nombre, "usuario": responsable.usuario_softguard,
            }
    return catalogo


def identificar_coordinador_softguard(numero):
    """Compatibilidad de consulta individual; la regla se comparte con los lotes."""
    return inferir_coordinador(consultar_historial_odt(numero), catalogo_coordinadores())


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


def _datos_asignacion(usuario, asignado_en, catalogo=None):
    datos = next((d for d in (catalogo if catalogo is not None else catalogo_coordinadores()).values()
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
    """Un lote: catálogo, responsables locales y, si hace falta, origen.

    Una falla no equivale a Sin identificar. Solo devuelve esa clasificación
    cuando la lectura terminó y no encontró un responsable inequívoco.
    """
    numeros = list(dict.fromkeys(numero_odt(n) for n in numeros))
    if len(numeros) > 250:
        raise ValueError("El lote admite como máximo 250 ODT.")
    if not numeros:
        return {}
    resultados = {}
    try:
        catalogo = catalogo_coordinadores()
        from .models import ODT
        from .casos_uso.proyeccion_coordinadores import resultado_local
        for odt in ODT.objects.filter(numero__in=numeros).select_related(
            "asignacion_coordinador", "responsable_local"
        ).only("numero", "asignacion_coordinador__usuario_coordinador",
               "asignacion_coordinador__asignado_en", "responsable_local__resultado",
               "responsable_local__firma_catalogo", "responsable_local__verificado_en"):
            asignacion = getattr(odt, "asignacion_coordinador", None)
            if asignacion is not None:
                resultados[odt.numero] = _datos_asignacion(
                    asignacion.usuario_coordinador, asignacion.asignado_en, catalogo)
                continue
            local = getattr(odt, "responsable_local", None)
            if local is not None:
                dato = resultado_local(local.resultado, local.firma_catalogo, local.verificado_en, catalogo)
                if dato is not None:
                    resultados[odt.numero] = dato
        pendientes = [n for n in numeros if n not in resultados]
        if pendientes:
            movimientos = {n: [] for n in pendientes}
            for movimiento in consultar_eventos_coordinadores(pendientes, catalogo):
                numero = numero_odt(movimiento.get("NumeroODT"))
                if numero in movimientos:
                    movimientos[numero].append(movimiento)
            for numero, eventos in movimientos.items():
                resultados[numero] = inferir_coordinador(eventos, catalogo)
        return resultados
    except Exception:
        # No exponer errores del driver ni atribuir fallos a Sin identificar.
        raise CoordinadoresNoDisponibles(resultados) from None
