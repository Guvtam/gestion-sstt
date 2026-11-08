"""Construcción del documento con catálogo e historiales ya obtenidos; sin ORM ni SQL."""
from decimal import Decimal
from io import BytesIO
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Spacer, PageBreak
from ..dominio.cuentas import tipo_cliente_cuenta, normalizar_codigo_cuenta
from .componentes import P, fecha, dinero, tabla, pie_pagina, banda_titulo
from .imagenes import comentario_con_imagen

def construir_documento_contratista(
    nombre_contratista,
    registros_contratista,
    desde,
    hasta,
    requisicion="",
    historico=False,
    datos_contratista=None,
    incluir_bancarios=False,
    *, catalogo_clientes, historiales,
):
    """
    Genera y devuelve los bytes de UN PDF.

    registros_contratista:
        [
            (odt, servicio, monto, contratista),
            ...
        ]
    """

    def tipo_cliente_pdf(odt):
        tipo = tipo_cliente_cuenta(odt.cuenta_completa, catalogo_clientes)
        return "Sin clasificar" if tipo == "SIN_CLASIFICAR" else tipo

    def ceco_pdf(odt):
        cuenta = catalogo_clientes.get(normalizar_codigo_cuenta(odt.cuenta_completa))
        return (cuenta.ceco or "").strip() or "Revisar CECO" if cuenta else "Revisar CECO"

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=13 * mm,
        bottomMargin=17 * mm,
        title=f"Reporte SSTT - {nombre_contratista}",
    )

    ancho = landscape(A4)[0] - 28 * mm
    story = []

    # --------------------------------------------------------
    # ENCABEZADO
    # --------------------------------------------------------

    story.append(
        P("Reporte de Servicio Técnico", "title")
    )

    story.append(
        P(
            f"Contratista: {nombre_contratista}",
            "bold",
        )
    )

    story.append(Spacer(1, 3 * mm))

    if datos_contratista is None:
        story.append(P("Datos del contratista: sin vínculo validado con el catálogo SSTT.", "bold"))
    else:
        c = datos_contratista
        story.append(P("Datos del contratista", "bold"))
        story.append(Spacer(1, 2 * mm))
        correos = "; ".join(v for v in (c.correo, c.correo_alternativo) if v)
        campos = [
            ("Nombre", c.nombre),
            ("Nombre / razón social", c.nombre_empresa),
            ("RUT", c.rut),
            ("Teléfono", c.fono),
            ("Correo", correos),
            ("Ciudad", c.ciudad),
            ("Banco", c.banco if incluir_bancarios else "Acceso restringido"),
            ("Tipo de cuenta", c.tipo_cuenta if incluir_bancarios else "Acceso restringido"),
            ("Número de cuenta", c.numero_cuenta if incluir_bancarios else "Acceso restringido"),
            ("Categoría", c.categoria),
        ]
        filas = []
        for i in range(0, len(campos), 2):
            izquierda, derecha = campos[i:i+2]
            filas.append([P(izquierda[0], "bold"), P(izquierda[1] or "No registrado"),
                          P(derecha[0], "bold"), P(derecha[1] or "No registrado")])
        story.append(tabla(filas, [ancho * .14, ancho * .36, ancho * .14, ancho * .36]))
    story.append(Spacer(1, 4 * mm))

    subtotal = sum(
        (
            Decimal(str(registro[2] or 0))
            for registro in registros_contratista
        ),
        Decimal("0"),
    )

    resumen = tabla(
        [
            [
                P("CONTRATISTA", "white"),
                P("PERÍODO", "white"),
                P("REQUISICIÓN", "white"),
                P("ODT", "white"),
                P("TOTAL", "white"),
            ],
            [
                P(nombre_contratista, "bold"),
                P(
                    f"{desde:%d-%m-%Y} "
                    f"al {hasta:%d-%m-%Y}",
                    "bold",
                ),
                P(requisicion or "—", "bold"),
                P(len(registros_contratista), "bold"),
                P(dinero(subtotal), "bold"),
            ],
        ],
        [
            ancho * 0.30,
            ancho * 0.25,
            ancho * 0.17,
            ancho * 0.08,
            ancho * 0.20,
        ],
        header=True,
    )

    story.append(resumen)
    story.append(Spacer(1, 5 * mm))

    # --------------------------------------------------------
    # 1. RESUMEN DE SERVICIOS
    # --------------------------------------------------------

    titulo = "1. Listado de ODT facturadas" if historico else "1. Listado de ODT aprobadas"
    story.append(P(titulo, "bold"))
    story.append(Spacer(1, 2 * mm))
    listado = [[P(columna, "white") for columna in (
        "ODT", "Fecha finalización", "Cuenta", "Servicio", "Tipo cliente", "CECO", "Monto"
    )]]
    for odt, servicio, monto, _ in registros_contratista:
        listado.append([
            P(odt.numero), P(fecha(odt.fecha_finalizacion)), P(odt.cuenta_completa),
            P(servicio), P(tipo_cliente_pdf(odt)), P(ceco_pdf(odt)), P(dinero(monto), "bold"),
        ])
    story.append(tabla(listado, [
        ancho * 0.06, ancho * 0.13, ancho * 0.25,
        ancho * 0.24, ancho * 0.09, ancho * 0.09, ancho * 0.14,
    ], header=True))
    story.append(PageBreak())

    # --------------------------------------------------------
    # 2. HISTORIAL DE ACCIONES POR ODT
    # --------------------------------------------------------

    story.append(
        P("2. Historial de acciones por ODT", "bold")
    )

    story.append(Spacer(1, 3 * mm))

    detalle_widths = [ancho * v for v in
                      (0.06, 0.11, 0.15, 0.08, 0.12, 0.22, 0.08, 0.08, 0.10)]

    detalle_heads = [
        "Número",
        "Fecha finalización",
        "Cuenta",
        "Localidad",
        "Servicio",
        "Observaciones (insumos)",
        "Tipo cliente",
        "CECO",
        (
            "Monto facturado"
            if historico
            else "Monto aprobado"
        ),
    ]

    for odt, servicio, monto, _ in registros_contratista:

        # ----------------------------------------------------
        # IDENTIFICACIÓN DE LA ODT
        # ----------------------------------------------------

        texto_banda = (
            f"ODT {odt.numero} · "
            f"{odt.cuenta_completa or 'Sin cuenta'}"
        )

        story.append(
            banda_titulo(texto_banda, ancho)
        )

        # ----------------------------------------------------
        # DETALLE DEL SERVICIO
        # ----------------------------------------------------

        detalle = tabla(
            [
                [
                    P(h, "white")
                    for h in detalle_heads
                ],
                [
                    P(odt.numero, "bold"),
                    P(fecha(odt.fecha_finalizacion)),
                    P(odt.cuenta_completa),
                    P(odt.localidad),
                    P(servicio),
                    P(odt.observaciones_insumos),
                    P(tipo_cliente_pdf(odt)),
                    P(ceco_pdf(odt)),
                    P(dinero(monto), "bold"),
                ],
            ],
            detalle_widths,
            header=True,
        )

        story.append(detalle)

        # ----------------------------------------------------
        # HISTORIAL SOFTGUARD
        # ----------------------------------------------------

        story.append(
            banda_titulo(
                "HISTORIAL ODT · ACCIONES Y COMENTARIOS",
                ancho,
            )
        )

        # No ocultar errores: Finanzas necesita
        # el historial completo de cada ODT.
        movimientos = historiales[odt.numero]

        hist = [
            [
                P("Fecha y hora", "white"),
                P("Acción", "white"),
                P("Usuario", "white"),
                P(
                    "Comentarios / observación",
                    "white",
                ),
            ]
        ]

        for movimiento in movimientos or []:

            hist.append([
                P(
                    fecha(
                        movimiento.get("FechaHora")
                    )
                ),
                P(movimiento.get("Accion")),
                P(
                    movimiento.get("NombreUsuario")
                    or movimiento.get("CorreoUsuario")
                    or "No identificado"
                ),
                comentario_con_imagen(
                    movimiento.get("Observacion")
                ),
            ])

        if not movimientos:
            hist.append([
                P("—"),
                P("Sin movimientos"),
                P("—"),
                P(
                    "No hay acciones registradas "
                    "en SoftGuard."
                ),
            ])

        story.append(
            tabla(
                hist,
                [
                    ancho * 0.16,
                    ancho * 0.16,
                    ancho * 0.21,
                    ancho * 0.47,
                ],
                header=True,
            )
        )

        story.append(Spacer(1, 6 * mm))

    # --------------------------------------------------------
    # CONSTRUIR PDF DEL CONTRATISTA
    # --------------------------------------------------------

    doc.build(
        story,
        onFirstPage=pie_pagina,
        onLaterPages=pie_pagina,
    )

    return buffer.getvalue()

