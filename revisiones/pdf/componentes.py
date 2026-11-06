"""Primitivas de presentación PDF; sin HTTP ni consultas de datos."""
import re
from datetime import date, datetime
from decimal import Decimal
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Table, TableStyle

NAVY = colors.HexColor("#17324F")
BLUE = colors.HexColor("#42688D")
LIGHT = colors.HexColor("#F5F7FA")
GRAY = colors.HexColor("#64748B")
BORDER = colors.HexColor("#D5DEE7")


# ============================================================
# ESTILOS
# ============================================================

STYLES = {
    "title": ParagraphStyle(
        "sstt_title",
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=19,
        textColor=NAVY,
        spaceAfter=7,
    ),
    "normal": ParagraphStyle(
        "sstt_normal",
        fontName="Helvetica",
        fontSize=8,
        leading=11,
    ),
    "small": ParagraphStyle(
        "sstt_small",
        fontName="Helvetica",
        fontSize=7,
        leading=10,
    ),
    "bold": ParagraphStyle(
        "sstt_bold",
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=11,
    ),
    "white": ParagraphStyle(
        "sstt_white",
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=11,
        textColor=colors.white,
    ),
    "history_title": ParagraphStyle(
        "sstt_history_title",
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=11,
        textColor=colors.white,
    ),
}


def P(value, style="small"):
    if value is None or value == "":
        texto = "—"
    else:
        texto = str(value)

    return Paragraph(
        escape(texto).replace("\n", "<br/>"),
        STYLES[style],
    )



def fecha(valor):
    if not valor:
        return "—"

    if isinstance(valor, datetime):
        return valor.strftime("%d-%m-%Y %H:%M")

    if isinstance(valor, date):
        return valor.strftime("%d-%m-%Y")

    return str(valor)


def dinero(valor):
    valor_decimal = Decimal(str(valor or 0))

    return "$ " + f"{valor_decimal:,.0f}".replace(
        ",", "."
    )


def tabla(data, widths, header=False):
    t = Table(
        data,
        colWidths=widths,
        repeatRows=1 if header else 0,
        hAlign="LEFT",
    )

    comandos = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]

    if header:
        comandos.extend([
            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                NAVY,
            ),
            (
                "ROWBACKGROUNDS",
                (0, 1),
                (-1, -1),
                [colors.white, LIGHT],
            ),
        ])

    t.setStyle(TableStyle(comandos))
    return t


def pie_pagina(canvas, doc):
    canvas.saveState()

    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GRAY)

    canvas.drawString(
        14 * mm,
        10 * mm,
        "Sistema SSTT · Reporte de servicios aprobados",
    )

    canvas.drawRightString(
        283 * mm,
        10 * mm,
        f"Página {doc.page}",
    )

    canvas.restoreState()


def banda_titulo(texto, ancho):
    t = Table(
        [[P(texto, "white")]],
        colWidths=[ancho],
    )

    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BLUE),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    return t


def nombre_archivo_seguro(nombre):
    nombre = re.sub(
        r"[^\w-]+",
        "_",
        str(nombre),
    ).strip("_")

    return nombre[:100] or "Contratista"


