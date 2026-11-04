
"""
Exportación de pagos SSTT.

HISTORIAL:
    Genera un ZIP con un PDF independiente por contratista.
    Utiliza los servicios y montos guardados en facturación.

BANDEJA:
    Mantiene la exportación individual de PDF.

Cada PDF incluye:
    - Identificación del contratista
    - Período y requisición
    - Resumen de servicios
    - Montos
    - Detalle de cada ODT
    - Historial de acciones de SoftGuard
    - Observaciones, imágenes y firmas disponibles
"""

import base64
import binascii
import re
import zipfile

from collections import OrderedDict
from datetime import date, datetime
from decimal import Decimal
from html.parser import HTMLParser
from io import BytesIO
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
from xml.sax.saxutils import escape

from django.conf import settings
from django.contrib.auth.decorators import (
    login_required,
    permission_required,
)
from django.db.models import Q
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image as PDFImage,
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    PageBreak,
)

from .models import ODT
from .facturacion_models import (
    PeriodoFacturacion,
    FacturacionODT,
)
from .servicios_sql import consultar_historial_odt
from .views import condicion_aprobada


# ============================================================
# COLORES
# ============================================================

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


# ============================================================
# IMÁGENES Y FIRMAS DEL HISTORIAL
# ============================================================

class ExtractorImagenesHTML(HTMLParser):

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.textos = []
        self.imagenes = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()

        if tag == "img":
            atributos = dict(attrs)
            src = atributos.get("src", "").strip()

            if src:
                self.imagenes.append(src)

        elif tag == "br":
            self.textos.append("\n")

        elif tag in ("p", "div", "li"):
            self.textos.append("\n")

    def handle_data(self, data):
        self.textos.append(data)


class SinRedireccion(HTTPRedirectHandler):

    def redirect_request(
        self, req, fp, code, msg, headers, newurl
    ):
        return None


def descargar_imagen_pdf(src):
    """
    Admite imágenes base64 y HTTPS de dominios
    configurados en settings.SSTT_IMAGE_HOSTS.
    """

    if not src:
        return None

    src = str(src).strip()

    if src.startswith("data:image/"):
        try:
            encabezado, contenido = src.split(",", 1)

            if ";base64" not in encabezado.lower():
                return None

            if len(contenido) > 8_000_000:
                return None

            return base64.b64decode(
                contenido,
                validate=True,
            )

        except (ValueError, binascii.Error):
            return None

    url = urlparse(src)

    if url.scheme != "https":
        return None

    hosts_permitidos = set(
        getattr(settings, "SSTT_IMAGE_HOSTS", [])
    )

    if (
        not url.hostname
        or url.hostname not in hosts_permitidos
    ):
        return None

    try:
        solicitud = Request(
            src,
            headers={"User-Agent": "SSTT-PDF/1.0"},
        )

        opener = build_opener(SinRedireccion())

        with opener.open(
            solicitud,
            timeout=8,
        ) as respuesta:

            tipo = respuesta.headers.get_content_type()

            if tipo not in (
                "image/png",
                "image/jpeg",
                "image/gif",
            ):
                return None

            datos = respuesta.read(5_000_001)

            if len(datos) > 5_000_000:
                return None

            return datos

    except Exception:
        return None


def imagen_para_pdf(
    datos,
    ancho_maximo=75 * mm,
    alto_maximo=35 * mm,
):
    try:
        imagen = ImageReader(BytesIO(datos))
        ancho, alto = imagen.getSize()

        if ancho <= 0 or alto <= 0:
            return None

        escala = min(
            ancho_maximo / ancho,
            alto_maximo / alto,
            1,
        )

        flujo = PDFImage(
            BytesIO(datos),
            width=ancho * escala,
            height=alto * escala,
        )

        flujo.hAlign = "LEFT"
        return flujo

    except Exception:
        return None


def comentario_con_imagen(observacion):
    """
    Extrae texto e imágenes del HTML de SoftGuard.
    """

    if not observacion:
        return P("—")

    contenido = str(observacion)
    extractor = ExtractorImagenesHTML()

    try:
        extractor.feed(contenido)
        extractor.close()

    except Exception:
        return P(contenido)

    texto = "".join(extractor.textos).strip()
    elementos = []

    if texto:
        elementos.append(P(texto))

    for src in extractor.imagenes:
        datos = descargar_imagen_pdf(src)

        if datos:
            imagen = imagen_para_pdf(datos)

            if imagen:
                elementos.append(Spacer(1, 2 * mm))
                elementos.append(imagen)
                continue

        elementos.append(
            P("Imagen o firma no disponible en PDF.")
        )

    if not elementos:
        elementos.append(P("—"))

    return elementos


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

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


# ============================================================
# GENERAR PDF INDIVIDUAL
# ============================================================

def generar_pdf_contratista(
    nombre_contratista,
    registros_contratista,
    desde,
    hasta,
    requisicion="",
    historico=False,
):
    """
    Genera y devuelve los bytes de UN PDF.

    registros_contratista:
        [
            (odt, servicio, monto, contratista),
            ...
        ]
    """

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

    titulo = (
        "1. Resumen de servicios facturados"
        if historico
        else "1. Resumen de servicios aprobados"
    )

    story.append(P(titulo, "bold"))
    story.append(Spacer(1, 2 * mm))

    resumen_servicios = OrderedDict()
    for odt, servicio, monto, _ in registros_contratista:
        nombre = str(servicio or "Sin servicio").strip()
        normalizado = nombre.upper().replace("Ó", "O").replace("Á", "A")
        if "CORRECTIVA" in normalizado and "SIN COBRO" in normalizado:
            categoria = "Mantención correctiva sin cobro"
        elif "CORRECTIVA" in normalizado and "CON COBRO" in normalizado:
            categoria = "Mantención correctiva con cobro"
        elif "RENOVACION" in normalizado:
            categoria = "Renovación"
        elif "PREVENTIVO" in normalizado:
            categoria = "Mantenimiento preventivo"
        else:
            categoria = "Otros servicios"
        grupo = resumen_servicios.setdefault(categoria, {"cantidad": 0, "monto": Decimal("0")})
        grupo["cantidad"] += 1
        grupo["monto"] += Decimal(str(monto or 0))

    listado = [[P("SERVICIO", "white"), P("CANTIDAD ODT", "white"), P("MONTO", "white")]]
    for nombre, datos in resumen_servicios.items():
        listado.append([P(nombre), P(datos["cantidad"]), P(dinero(datos["monto"]), "bold")])
    listado.append([P("TOTAL", "bold"), P(len(registros_contratista), "bold"), P(dinero(subtotal), "bold")])
    story.append(tabla(listado, [ancho * 0.60, ancho * 0.15, ancho * 0.25], header=True))
    story.append(PageBreak())

    # --------------------------------------------------------
    # 2. HISTORIAL DE ACCIONES POR ODT
    # --------------------------------------------------------

    story.append(
        P("2. Historial de acciones por ODT", "bold")
    )

    story.append(Spacer(1, 3 * mm))

    detalle_widths = [
        ancho * 0.085,
        ancho * 0.13,
        ancho * 0.15,
        ancho * 0.10,
        ancho * 0.12,
        ancho * 0.23,
        ancho * 0.095,
        ancho * 0.09,
    ]

    detalle_heads = [
        "Número",
        "Fecha finalización",
        "Cuenta",
        "Localidad",
        "Servicio",
        "Observaciones (insumos)",
        "Tipo cliente",
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
                    P(odt.tipo_cliente),
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
        movimientos = consultar_historial_odt(
            odt.numero
        )

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


# ============================================================
# VISTA PRINCIPAL DE EXPORTACIÓN
# ============================================================

@login_required
@permission_required(
    "revisiones.exportar_pagos_sstt",
    raise_exception=True,
)
def exportar_aprobados_pdf(request):

    periodo_id = request.GET.get(
        "periodo",
        "",
    ).strip()

    historico = bool(periodo_id)

    # ========================================================
    # OPCIÓN 1: HISTORIAL DE FACTURACIÓN
    # GENERAR ZIP CON UN PDF POR CONTRATISTA
    # ========================================================

    if historico:

        if not periodo_id.isdigit():
            return HttpResponseBadRequest(
                "Período inválido."
            )

        periodo = get_object_or_404(
            PeriodoFacturacion,
            pk=int(periodo_id),
        )

        desde = periodo.fecha_desde
        hasta = periodo.fecha_hasta

        # Obtener exclusivamente las ODT guardadas
        # en este período de facturación.
        items = list(
            FacturacionODT.objects
            .filter(
                facturacion__periodo=periodo
            )
            .select_related(
                "odt",
                "facturacion",
            )
            .order_by(
                "facturacion__contratista",
                "odt__numero",
            )
        )

        if not items:
            return HttpResponseBadRequest(
                "El período no tiene ODT facturadas."
            )

        # ----------------------------------------------------
        # AGRUPAR ODT POR CONTRATISTA
        # ----------------------------------------------------

        grupos = OrderedDict()
        requisiciones = {}

        for item in items:

            nombre = item.facturacion.contratista

            if nombre not in grupos:
                grupos[nombre] = []

            grupos[nombre].append((
                item.odt,
                item.servicio_facturado,
                (
                    item.monto_facturado
                    if item.monto_facturado is not None
                    else Decimal("0")
                ),
                nombre,
            ))

            requisiciones[nombre] = (
                item.facturacion.numero_requisicion
            )

        # ----------------------------------------------------
        # GENERAR UN PDF INDEPENDIENTE POR CONTRATISTA
        # ----------------------------------------------------

        archivo_zip = BytesIO()

        try:
            with zipfile.ZipFile(
                archivo_zip,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
            ) as zip_salida:

                for indice, (
                    nombre_contratista,
                    registros_contratista,
                ) in enumerate(grupos.items(), start=1):

                    # Generar solamente las ODT
                    # del contratista actual.
                    pdf_bytes = generar_pdf_contratista(
                        nombre_contratista=nombre_contratista,
                        registros_contratista=registros_contratista,
                        desde=desde,
                        hasta=hasta,
                        requisicion=requisiciones.get(
                            nombre_contratista,
                            "",
                        ),
                        historico=True,
                    )

                    nombre_seguro = nombre_archivo_seguro(
                        nombre_contratista
                    )

                    nombre_pdf = (
                        f"{indice:02d}_"
                        f"{nombre_seguro}_"
                        f"{desde:%Y%m%d}_"
                        f"{hasta:%Y%m%d}.pdf"
                    )

                    # Guardar cada PDF como archivo
                    # independiente dentro del ZIP.
                    zip_salida.writestr(
                        nombre_pdf,
                        pdf_bytes,
                    )

        except Exception as error:
            # Evitar entregar un ZIP incompleto.
            return HttpResponse(
                (
                    "No fue posible generar todos los "
                    "reportes del período. "
                    f"Detalle: {error}"
                ),
                status=503,
                content_type=(
                    "text/plain; charset=utf-8"
                ),
            )

        # ----------------------------------------------------
        # DESCARGAR ZIP DEL PERÍODO
        # ----------------------------------------------------

        respuesta = HttpResponse(
            archivo_zip.getvalue(),
            content_type="application/zip",
        )

        respuesta["Content-Disposition"] = (
            'attachment; filename="'
            f"Facturacion_SSTT_{desde:%Y%m%d}_"
            f'{hasta:%Y%m%d}.zip"'
        )

        return respuesta

    # ========================================================
    # OPCIÓN 2: BANDEJA
    # MANTENER EXPORTACIÓN PDF INDIVIDUAL
    # ========================================================

    contratista = request.GET.get(
        "contratista",
        "",
    ).strip()

    desde_texto = request.GET.get(
        "fecha_desde",
        "",
    ).strip()

    hasta_texto = request.GET.get(
        "fecha_hasta",
        "",
    ).strip()

    if (
        not contratista
        or not desde_texto
        or not hasta_texto
    ):
        return HttpResponseBadRequest(
            "Selecciona un contratista y ambas "
            "fechas antes de exportar."
        )

    try:
        desde = date.fromisoformat(desde_texto)
        hasta = date.fromisoformat(hasta_texto)

    except ValueError:
        return HttpResponseBadRequest(
            "Las fechas no tienen un formato válido."
        )

    if desde > hasta:
        return HttpResponseBadRequest(
            "La fecha inicial no puede superar "
            "la fecha final."
        )

    # --------------------------------------------------------
    # OBTENER ODT APROBADAS
    # --------------------------------------------------------

    registros = (
        ODT.objects
        .select_related("revision")
        .filter(
            condicion_aprobada(),
            contratista=contratista,
            fecha_finalizacion__date__gte=desde,
            fecha_finalizacion__date__lte=hasta,
        )
        .order_by(
            "fecha_finalizacion",
            "numero",
        )
    )

    # --------------------------------------------------------
    # CONSERVAR FILTROS DE LA BANDEJA
    # --------------------------------------------------------

    estado = request.GET.get(
        "estado",
        "",
    ).strip()

    if estado:
        registros = registros.filter(
            estado_softguard=estado
        )

    tipo_cliente = request.GET.get(
        "tipo_cliente",
        "",
    ).strip()

    if tipo_cliente:
        registros = registros.filter(
            tipo_cliente=tipo_cliente
        )

    servicios = request.GET.getlist("servicios")

    if servicios:
        registros = registros.filter(
            Q(
                servicio_editado__isnull=True,
                servicio__in=servicios,
            )
            |
            Q(
                servicio_editado__in=servicios
            )
        )

    q = request.GET.get(
        "q",
        "",
    ).strip()

    if q:

        filtro = (
            Q(contratista__icontains=q)
            | Q(tecnico__icontains=q)
            | Q(cuenta_completa__icontains=q)
            | Q(servicio__icontains=q)
            | Q(servicio_editado__icontains=q)
            | Q(direccion__icontains=q)
        )

        if q.isdigit():
            filtro |= Q(numero=int(q))

        registros = registros.filter(filtro)

    odts = list(registros)

    if not odts:
        return HttpResponseBadRequest(
            "No existen ODT aprobadas para "
            "este contratista y período."
        )

    # --------------------------------------------------------
    # PREPARAR SERVICIOS Y MONTOS APROBADOS
    # --------------------------------------------------------

    detalles = []

    for odt in odts:

        servicio = (
            odt.servicio_editado
            if odt.servicio_editado is not None
            else odt.servicio
        )

        monto = (
            odt.valor_pago_editado
            if odt.valor_pago_editado is not None
            else (
                odt.valor_pago_tecnico
                or Decimal("0")
            )
        )

        detalles.append((
            odt,
            servicio,
            monto,
            odt.contratista,
        ))

    # --------------------------------------------------------
    # GENERAR UN ÚNICO PDF PARA LA BANDEJA
    # --------------------------------------------------------

    try:
        pdf_bytes = generar_pdf_contratista(
            nombre_contratista=contratista,
            registros_contratista=detalles,
            desde=desde,
            hasta=hasta,
            requisicion="",
            historico=False,
        )

    except Exception as error:
        return HttpResponse(
            (
                "No fue posible generar el PDF. "
                f"Detalle: {error}"
            ),
            status=503,
            content_type="text/plain; charset=utf-8",
        )

    respuesta = HttpResponse(
        pdf_bytes,
        content_type="application/pdf",
    )

    nombre_seguro = nombre_archivo_seguro(
        contratista
    )

    respuesta["Content-Disposition"] = (
        'attachment; filename="'
        f"Reporte_SSTT_{nombre_seguro}_"
        f"{desde:%Y%m%d}_"
        f'{hasta:%Y%m%d}.pdf"'
    )

    return respuesta
