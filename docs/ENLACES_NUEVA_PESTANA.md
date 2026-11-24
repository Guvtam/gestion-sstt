# Enlaces de consulta en otra pestaña

La base compartida de Revisiones y Contratistas carga `enlaces_pestanas.js`.
Los enlaces HTTP(S) de consulta, incluidos número de ODT, detalle de calendario
y enlaces de detalle/historial presentados como texto, usan `target="_blank"`
y `rel="noopener"`. Conservan URL, filtros y rel existentes. No se usa
window.open ni se intercepta la navegación con preventDefault; funcionan clic,
Ctrl/Cmd, botón central y enlaces añadidos después de cargar (delegación en captura).

Botones reales y enlaces presentados como botones (.btn, .stats-btn,
.fact-secondary, .hist-secondary), menú, Volver, paginación, filtros, tarjetas
y gráficos que actúan como filtros conservan su comportamiento. No se cambian
formularios ni eventos de Guardar, facturar, confirmar, editar o descargar.
Los downloads explícitos, anclas internas, mailto/tel/javascript y destinos
explícitos distintos de _blank quedan intactos. Se puede marcar un control
nuevo con `data-sstt-misma-pestana` para conservar la pestaña actual.

No se usa una etiqueta base target global porque también afectaría formularios.
No se añade noreferrer: se mantiene el referente de navegación para los regresos
internos. No cambia permisos ni acceso de otros usuarios: cada pestaña mantiene
las comprobaciones del servidor. La administración estándar Django y los PDFs
no usan esta base operativa y no se alteran. Sin JavaScript rige el HTML original.

## Despliegue Raspberry

Tras integrar el PR, actualizar código, collectstatic, copiar estáticos a Nginx
y reiniciar sstt-prueba como habitualmente. No requiere migraciones ni permisos.
Recargar Ctrl+F5.

Verificar en bandeja y calendario de calvarez: ODT abre otra pestaña, origen
permanece con filtros/posición. Comprobar menú, Volver, filtros, paginación y
botones Guardar/Historial existentes: no abren pestañas adicionales. Un botón
Historial que abre modal continúa siendo modal; solo enlaces reales cambian.
