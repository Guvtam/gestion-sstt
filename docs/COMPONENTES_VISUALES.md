# Componentes visuales compartidos

La plantilla base_operativa.html concentra el documento HTML, idioma, viewport,
hoja común bandeja.css y encabezado de Gestión de pagos SSTT.

Las pantallas de facturar período, historial de facturación, detalle de ODT
facturadas e historial de requisición heredan esta base. Cada una declara:

- Título del navegador y subtítulo del encabezado.
- Hojas específicas de su pantalla.
- Acciones del encabezado, conservando enlaces y contexto de retorno.
- Contenido principal y scripts específicos, ejecutados después del contenido.

Se mantienen clases CSS, identificadores, formularios, CSRF, navegación y scripts
existentes. La base no incorpora enlaces operativos nuevos ni decide permisos.
Los permisos se siguen comprobando en las vistas y casos de uso.

La entrega reduce duplicación; no rediseña las tablas ni los filtros.
Quedan pendientes bandeja, análisis, preventivos y administración, además de
extraer componentes de filtros y mensajes cuando sus contratos estén alineados.
No requiere migraciones ni modifica archivos estáticos.

Validación: suite completa, controles Django y comparación del contenido main
y de todos los scripts contra la versión anterior. No se realizó una revisión
visual en navegador ni se accedió al servidor de despliegue.
