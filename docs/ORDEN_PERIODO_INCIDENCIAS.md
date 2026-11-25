# Ordenamiento, incidencias históricas y período inicial

## Bandeja

Se agregan Ordenar por y Dirección al formulario superior. Opciones: Cuenta,
Número de ODT, Contratista, Coordinador y Fecha de finalización; ascendente o
descendente. Orden habitual conserva la prioridad anterior de correcciones.
Al elegir un campo explícito se ordena por ese campo en todo el conjunto filtrado,
antes de paginar, con desempates estables. Las fechas nulas van al final.
Las FDP de jiturriaga siguen al final, en ambas direcciones, conservando su marca.
No cambian permisos, bloqueos, campos ni estados de las ODT.

El orden por coordinador usa el mismo nombre que muestra la bandeja, resuelto
para las ODT del conjunto previamente autorizado y filtrado. Solo se proyectan
PK, número y bandera FDP; se cargan los modelos de la página visible después.
Reutiliza el resolver por lotes y caché de la petición, sin generar un CASE de
SQL por cada ODT. Los responsables no disponibles quedan al final; no se usan
estos datos de presentación para conceder acceso. Ordenar por coordinador exige
resolver todo el conjunto filtrado y puede costar más que ordenar por un campo
local de la ODT.

Los parámetros orden/direccion se validan contra una lista permitida. Se
conservan en paginación, retorno de ediciones y descarga Excel/PDF de selección.

## Referencia de incidencias

En Gestión de pagos y Pagos nueva instalación, 90 / 60 / 30 días se calculan
hasta Finalización hasta, incluido su día completo, en America/Santiago.
Cada ventana contiene esa cantidad de días calendario, terminando en el día
seleccionado: límite inferior incluido y medianoche del día siguiente excluida.

Se mantienen misma cuenta exacta y mismo contratista, estado Finalizado,
exclusión de cuentas/contratistas vacíos y los umbrales de colores. La ODT actual
cuenta si cumple la ventana; el rango Desde no limita el historial necesario
para calcular las incidencias. No se cuentan registros posteriores a Hasta.

Análisis ODT utiliza la misma referencia Hasta para sus métricas de incidencias.
La métrica por cuenta conserva su agrupación por código y cualquier contratista;
el ranking Top 50 sigue usando únicamente el período filtrado.
ODT por creación conserva su referencia actual: su filtro Hasta es de creación,
no de finalización. Sin Hasta, se conserva la referencia del reloj actual.
Los filtros inválidos conservan el aviso y comportamiento previo de la página.

## Fechas iniciales según facturación

Para el 25/11/2026:

| Situación del período 21/10–20/11 | Desde | Hasta |
|---|---|---|
| Sin facturar o parcialmente facturado con ODT elegibles pendientes | 21/10/2026 | 20/11/2026 |
| Con facturación emitida y sin ODT elegibles pendientes | 21/11/2026 | 25/11/2026 |

Se reutiliza odts_facturables y se comprueba ausencia de item_facturacion:
finalizadas, con contratista, servicio efectivo y aprobación efectiva vigentes.
Sin revisión y POR_REVISAR conservan su aprobación actual; rechazadas no bloquean.
Monto cero sigue siendo elegible si las reglas actuales lo permiten.
Se examinan todos los contratistas del alcance inicial de pagos, no solo un
contratista, búsqueda o selección de montos que deje pendientes fuera de vista.

La bandeja general usa sus servicios principales predeterminados. Pagos nueva
instalación usa únicamente instalación genérica y sus facturas autorizadas,
excluyendo Cruzverde. Una cabecera de período vacía o la ausencia de registros
no equivale a una facturación emitida. No se adelanta al día 21 antes de que el
período termine; nunca se genera Desde posterior a Hasta.

Estas fechas solo sustituyen parámetros ausentes. Fechas manuales, incluso
vacías, se respetan. ODT por creación mantiene sus fechas iniciales anteriores.
Los filtros efectivos se fijan en la URL antes de guardar posición o seleccionar
exportaciones. Una pantalla abierta mantiene su período aunque otra persona
termine de facturarlo; volver a entrar por el menú calcula las fechas nuevamente.
No se modifica la confirmación por firma, la instantánea ni la facturación.

## Prueba local antes de desplegar

No hay migraciones ni cambios de permisos. El PR se entrega en borrador y no se
actualiza main ni la Raspberry automáticamente.

Si ya existe la copia local sstt-prueba-visual, detener runserver y ejecutar desde
esa carpeta, con el entorno virtual activado:

```powershell
git fetch origin
git switch --detach origin/mejora/orden-periodo-incidencias
python manage.py runserver 127.0.0.1:8001 --settings=config.settings_visual
```

Usar la copia db_visual.sqlite3 ya preparada; no copiar bases al servidor.
Comprobar todos los órdenes en varias páginas, FDP al final, edición conservando
posición y exportación con el mismo orden. Elegir una fecha Hasta histórica y
verificar que una atención posterior no incremente los contadores. En la copia,
probar facturación parcial y total con las reglas vigentes; no hacer pruebas
financieras ficticias sobre los datos del servidor.

Verificaciones automatizadas:

```bash
python manage.py check --settings=config.settings_test
python manage.py makemigrations --check --dry-run --settings=config.settings_test
python manage.py test contratistas revisiones --settings=config.settings_test
```
