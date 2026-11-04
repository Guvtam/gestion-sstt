from datetime import datetime
from .servicios_sql import consultar_historial_odt

COORDINADORES_SOFTGUARD = {
    4: {"nombre": "Josué Tapia", "usuario": "jtapia"},
    1256: {"nombre": "Jurguen Bicz", "usuario": "jbicz"},
    549: {"nombre": "Yasna Ramírez", "usuario": "yramirez"},
    1336: {"nombre": "Romina Silva", "usuario": "rsilva"},
}


def identificar_coordinador_softguard(numero):
    """Busca acciones de coordinadores autorizados en TODO el historial.

    Prioriza la última acción registrada por un coordinador. No presupone
    que quien creó la ODT siga siendo responsable. No escribe en BD.
    """
    resultado = {
        "id_softguard": None,
        "nombre": "Sin identificar",
        "usuario": None,
        "fecha_alta": None,
        "identificado": False,
        "accion_identificada": None,
        "fecha_ultima_accion": None,
    }

    movimientos = consultar_historial_odt(numero) or []
    candidatos = []
    for indice, movimiento in enumerate(movimientos):
        try:
            id_usuario = int(str(movimiento.get("IDUsuario") or "").strip())
        except (TypeError, ValueError):
            continue
        if id_usuario not in COORDINADORES_SOFTGUARD:
            continue
        fecha = movimiento.get("FechaHora")
        if isinstance(fecha, str):
            try:
                fecha = datetime.fromisoformat(fecha)
            except ValueError:
                fecha = None
        if not isinstance(fecha, datetime):
            fecha = None
        candidatos.append({
            "id_usuario": id_usuario,
            "fecha": fecha,
            "accion": str(movimiento.get("Accion") or "").strip().upper(),
            "indice": indice,
        })

    if not candidatos:
        return resultado

    # Si existen fechas, utilizar la última acción cronológica. Cuando
    # faltan fechas, no se puede afirmar quién fue el último responsable:
    # se identifica únicamente si todos los eventos apuntan al mismo usuario.
    fechados = [c for c in candidatos if c["fecha"] is not None]
    if fechados:
        ultimo = max(fechados, key=lambda c: c["fecha"])
        # En un empate entre distintos usuarios no atribuir arbitrariamente.
        empatados = {c["id_usuario"] for c in fechados if c["fecha"] == ultimo["fecha"]}
        if len(empatados) > 1:
            return resultado
    else:
        usuarios = {c["id_usuario"] for c in candidatos}
        if len(usuarios) != 1:
            return resultado
        ultimo = candidatos[0]

    altas = [c["fecha"] for c in candidatos if c["id_usuario"] == ultimo["id_usuario"] and c["accion"] == "ALTA" and c["fecha"] is not None]
    datos = COORDINADORES_SOFTGUARD[ultimo["id_usuario"]]
    resultado.update({
        "id_softguard": ultimo["id_usuario"],
        "nombre": datos["nombre"],
        "usuario": datos["usuario"],
        "fecha_alta": min(altas) if altas else None,
        "identificado": True,
        "accion_identificada": ultimo["accion"],
        "fecha_ultima_accion": ultimo["fecha"],
    })
    return resultado


def puede_asignar_coordinador(user):
    return (user.is_authenticated and user.is_active
            and user.get_username().strip().casefold() in ("admin", "jiturriaga"))


def identificar_coordinador_odt(numero):
    """La asignación local persiste y se utiliza en todas las vistas y filtros."""
    from .models import AsignacionCoordinadorODT
    asignacion = AsignacionCoordinadorODT.objects.filter(odt__numero=numero).first()
    if asignacion is None:
        return identificar_coordinador_softguard(numero)
    datos = next((d for d in COORDINADORES_SOFTGUARD.values()
                  if d["usuario"] == asignacion.usuario_coordinador), None)
    if datos is None:
        raise ValueError("Coordinador asignado no reconocido.")
    return {
        "nombre": datos["nombre"], "usuario": datos["usuario"],
        "identificado": True, "asignacion_manual": True,
        "fecha_ultima_accion": asignacion.asignado_en,
    }
