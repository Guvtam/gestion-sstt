
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
from .cuentas_utils import cargar_catalogo_cuentas, tipo_cliente_cuenta, normalizar_codigo_cuenta
from .facturacion_models import (
    PeriodoFacturacion,
    FacturacionODT,
    FacturacionContratista,
)
from .servicios_sql import consultar_historial_odt
from .consultas.pagos import condicion_aprobada


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

def datos_contratista_pdf(nombre):
    from contratistas.models import Contratista, EquivalenciaSoftGuard
    from contratistas.utils import normalizar_nombre
    clave = normalizar_nombre(nombre)
    equivalencia = EquivalenciaSoftGuard.objects.select_related("contratista").filter(
        clave_normalizada=clave
    ).first()
    if equivalencia:
        return equivalencia.contratista
    candidatos = [c for c in Contratista.objects.all()
                  if clave and clave in {normalizar_nombre(c.nombre), normalizar_nombre(c.nombre_softguard)}]
    return candidatos[0] if len(candidatos) == 1 else None


def generar_pdf_contratista(
    nombre_contratista,
    registros_contratista,
    desde,
    hasta,
    requisicion="",
    historico=False,
    datos_contratista=None,
    incluir_bancarios=False,
):
    """
    Genera y devuelve los bytes de UN PDF.

    registros_contratista:
        [
            (odt, servicio, monto, contratista),
            ...
        ]
    """

    catalogo_clientes = cargar_catalogo_cuentas(
        odt.cuenta_completa for odt, _, _, _ in registros_contratista
    )

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

        seleccion = None
        if request.GET.get("seleccion") == "1":
            valores = request.GET.getlist("facturacion")
            if not valores or any(not v.isdigit() for v in valores):
                return HttpResponseBadRequest("Selecciona al menos un contratista válido.")
            seleccion = {int(v) for v in valores}
            permitidos = set(FacturacionContratista.objects.filter(
                periodo=periodo, pk__in=seleccion
            ).values_list("pk", flat=True))
            if seleccion != permitidos:
                return HttpResponseBadRequest("La selección no corresponde al período.")
        consulta_items = FacturacionODT.objects.filter(facturacion__periodo=periodo)
        if seleccion is not None:
            consulta_items = consulta_items.filter(facturacion_id__in=seleccion)

        # Obtener exclusivamente las ODT guardadas
        # en este período de facturación.
        items = list(
            consulta_items.select_related(
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
                        datos_contratista=datos_contratista_pdf(nombre_contratista),
                        incluir_bancarios=request.user.has_perm("contratistas.ver_bancos_contratistas_sstt"),
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
            datos_contratista=datos_contratista_pdf(contratista),
            incluir_bancarios=request.user.has_perm("contratistas.ver_bancos_contratistas_sstt"),
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
