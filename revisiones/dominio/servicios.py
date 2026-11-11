"""Catálogo y clasificación comunes para operación e históricos."""
SERVICIOS_PRINCIPALES = (
    "MANTENCION CORRECTIVA CON COBRO",
    "MANTENCION CORRECTIVA SIN COBRO",
    "MANTENIMIENTO RENOVACIÓN",
    "MANTENIMIENTO PREVENTIVO",
    "MANTENIMIENTO ACUERDO COMERCIAL",
    "MANTENIMIENTO PRESUPUESTO",
    "MANTENIMIENTO NUEVA INSTALACION CRUZVERDE",
)
SERVICIOS_PREVENTIVOS = (
    "MANTENIMIENTO PREVENTIVO", "MANTENCION PREVENTIVA", "PREVENTIVO",
)
SERVICIOS_RENOVACION = (
    "RENOVACION", "RENOVACIÓN", "MANTENIMIENTO RENOVACION",
    "MANTENIMIENTO RENOVACIÓN", "MANTENCION RENOVACION", "MANTENCIÓN RENOVACIÓN",
)


def normalizar_servicio(valor):
    return " ".join(str(valor or "").upper().split()).translate(
        str.maketrans("ÁÉÍÓÚ", "AEIOU")
    )


def servicio_efectivo(original, editado):
    """Un valor editado vacío es explícito; solo None usa el original."""
    return original if editado is None else editado


NOMBRES_POR_CATEGORIA = {
    "correctiva_con_cobro": (SERVICIOS_PRINCIPALES[0],),
    "correctiva_sin_cobro": (SERVICIOS_PRINCIPALES[1],),
    "renovacion": SERVICIOS_RENOVACION,
    "preventivo": SERVICIOS_PREVENTIVOS,
    "acuerdo_comercial": (SERVICIOS_PRINCIPALES[4],),
    "presupuesto": (SERVICIOS_PRINCIPALES[5],),
    "nueva_instalacion_cruzverde": (SERVICIOS_PRINCIPALES[6],),
}

_CATEGORIAS = {
    normalizar_servicio(nombre): categoria
    for categoria, nombres in NOMBRES_POR_CATEGORIA.items()
    for nombre in nombres
}


def categoria_servicio(valor):
    return _CATEGORIAS.get(normalizar_servicio(valor), "otros")


def nombres_canonicos(categoria):
    return tuple(sorted({normalizar_servicio(n) for n in NOMBRES_POR_CATEGORIA[categoria]}))
