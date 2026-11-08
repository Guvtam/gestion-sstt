"""Imágenes y comentarios PDF; conserva límites, allowlist y bloqueo de redirecciones."""
import base64
import binascii
from html.parser import HTMLParser
from io import BytesIO
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
from django.conf import settings
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image as PDFImage, Spacer
from .componentes import P

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

