"""Composición de reportes a partir de filas autorizadas por el adaptador HTTP."""
from io import BytesIO
import zipfile
from ..cuentas_utils import cargar_catalogo_cuentas
from ..servicios_sql import consultar_historial_odt
from ..pdf.documento_contratista import construir_documento_contratista
from ..pdf.componentes import nombre_archivo_seguro


def generar_pdf_contratista(nombre_contratista, registros_contratista, desde, hasta,
                            requisicion="", historico=False, datos_contratista=None,
                            incluir_bancarios=False):
    filas = list(registros_contratista)
    catalogo = cargar_catalogo_cuentas(o.cuenta_completa for o, _, _, _ in filas)
    # La falta de historial por fallo del origen no se convierte en historial vacío.
    historiales = {}
    for odt, _, _, _ in filas:
        if odt.numero not in historiales:
            historiales[odt.numero] = consultar_historial_odt(odt.numero)
    return construir_documento_contratista(
        nombre_contratista, filas, desde, hasta, requisicion=requisicion,
        historico=historico, datos_contratista=datos_contratista,
        incluir_bancarios=incluir_bancarios, catalogo_clientes=catalogo, historiales=historiales,
    )


def generar_zip_facturacion(grupos, requisiciones, desde, hasta, *,
                            incluir_bancarios, generar_pdf, resolver_contratista):
    archivo = BytesIO()
    # Solo se devuelven bytes si todos los documentos terminaron correctamente.
    with zipfile.ZipFile(archivo, mode="w", compression=zipfile.ZIP_DEFLATED) as salida:
        for indice, (nombre, filas) in enumerate(grupos.items(), start=1):
            contenido = generar_pdf(
                nombre_contratista=nombre, registros_contratista=filas,
                desde=desde, hasta=hasta, requisicion=requisiciones.get(nombre, ""),
                historico=True, datos_contratista=resolver_contratista(nombre),
                incluir_bancarios=incluir_bancarios,
            )
            seguro = nombre_archivo_seguro(nombre)
            salida.writestr(f"{indice:02d}_{seguro}_{desde:%Y%m%d}_{hasta:%Y%m%d}.pdf", contenido)
    return archivo.getvalue()
