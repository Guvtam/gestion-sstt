"""El contratista operativo sigue al técnico informado por SoftGuard."""


def contratista_desde_tecnico(tecnico, actual=''):
    nombre = str(tecnico or '').strip()
    # Un origen vacío no aporta un reemplazo válido.
    return nombre[:150] if nombre else actual
