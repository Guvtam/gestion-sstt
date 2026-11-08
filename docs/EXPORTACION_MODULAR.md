# Exportación separada por responsabilidad

| Módulo | Responsabilidad |
|---|---|
| vistas/exportacion_pdf.py | Permisos, selección, validación de entrada y respuesta de descarga |
| consultas/exportacion_pdf.py | ODT aprobadas, items facturados y vínculo del contratista |
| casos_uso/exportacion_pdf.py | Preparación del reporte y composición completa del ZIP |
| pdf/documento_contratista.py | Construcción ReportLab con catálogo e historiales precargados |
| pdf/imagenes.py | Extracción y descarga controlada de imágenes y comentarios |
| pdf/componentes.py | Primitivas, estilos, tablas y pie de página |
| exportar_pdf.py | Imports compatibles para consumidores existentes |

El constructor del documento ya no consulta catálogo ni historial SQL.
Recibe filas, clasificación e historiales preparados. Las imágenes remotas
siguen pasando por su integración y pueden generar tráfico autorizado; no
se afirma que toda la construcción carezca de IO.

Se conserva el diseño del documento, los datos del contratista al comienzo,
el listado de ODT, CECO después del tipo de cliente, montos y servicios
facturados y el historial. El permiso bancario se resuelve en el adaptador
y se transmite explícitamente a cada documento.

La selección histórica se valida contra el período antes de obtener items.
Las consultas no deciden autorización y solo deben invocarse después de
autorizar en el adaptador. Generar un documento desde datos aportados no
concede acceso a una página ni amplía el conjunto de filas seleccionado.

La composición lee historial solo de las ODT entregadas, sin repetir una
misma ODT dentro de un reporte. Un error del origen no se reemplaza por
historial vacío. El ZIP solo se devuelve cuando todos sus PDF terminan.
La numeración de archivos evita colisiones entre nombres saneados iguales.

Se conservan los límites de imagen, allowlist HTTPS y bloqueo de redirecciones.
No se cambian validaciones, permisos o respuestas existentes en esta extracción.
Los errores HTTP conservan su tratamiento previo; no se aborda aquí la
revisión pendiente de configuración y protección del despliegue.

## Validación y límites

369 pruebas correctas, check sin incidencias y sin migraciones pendientes.
Los puntos de simulación de las pruebas se trasladan al módulo que utiliza la
dependencia; sus expectativas anteriores se conservan.

Las nuevas regresiones construyen y leen PDF reales sin consultas ORM desde
el constructor, verifican encabezados/CECO/acciones, nombres seguros del ZIP,
errores sin descarga parcial y la política de imágenes.
También se comparan las cinco definiciones del procesamiento de imágenes
contra la versión previa: misma estructura AST.

No requiere migraciones, sincronización ni cambios de estáticos.
No se modifican datos de las instalaciones. No se realizó revisión visual
en navegador ni prueba de carga de exportaciones grandes en el servidor.

El historial continúa consultándose por ODT y las imágenes se obtienen durante
la construcción. Límites globales de volumen y generación en segundo plano
requieren medición y una entrega posterior.
