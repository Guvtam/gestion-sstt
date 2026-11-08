"""Imports compatibles de exportación; usar módulos de consulta, caso de uso y PDF."""
from .vistas.exportacion_pdf import exportar_aprobados_pdf
from .casos_uso.exportacion_pdf import generar_pdf_contratista
from .consultas.exportacion_pdf import datos_contratista_pdf
from .pdf.imagenes import (
    ExtractorImagenesHTML, SinRedireccion, descargar_imagen_pdf,
    imagen_para_pdf, comentario_con_imagen,
)
from .pdf.componentes import (
    NAVY, BLUE, LIGHT, GRAY, BORDER, STYLES, P, fecha, dinero,
    tabla, pie_pagina, banda_titulo, nombre_archivo_seguro,
)
