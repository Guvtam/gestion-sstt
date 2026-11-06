"""Inferencia de responsable a partir de eventos; sin consultas ni escritura."""
from datetime import datetime


def inferir_coordinador(movimientos, catalogo):
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

    movimientos = movimientos or []
    candidatos = []
    for indice, movimiento in enumerate(movimientos):
        try:
            id_usuario = int(str(movimiento.get("IDUsuario") or "").strip())
        except (TypeError, ValueError):
            continue
        if id_usuario not in catalogo:
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
    datos = catalogo[ultimo["id_usuario"]]
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
