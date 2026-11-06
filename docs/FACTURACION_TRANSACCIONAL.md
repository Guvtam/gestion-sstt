# Facturación: consulta, previsualización y confirmación

## Organización implementada

| Módulo | Responsabilidad |
|---|---|
| `dominio/facturacion.py` | Período 21–20 y selección de filtros independiente de HTTP |
| `consultas/facturacion.py` | Consulta común de ODT finalizadas y aprobadas efectivamente |
| `casos_uso/facturacion.py` | Previsualización, confirmación transaccional y cambio de requisición |
| `casos_uso/autorizacion.py` | Permiso operativo compartido con edición/revisión de ODT |
| `facturacion.py` | Adaptadores HTTP, mensajes, renderizado y redirecciones |

La consulta de fechas usa límites de día en la zona horaria activa: inicio
inclusivo y día siguiente al fin exclusivo. Se evita aplicar una conversión de
fecha sobre la columna para ese filtro, preservando la inclusión del día 20.
No se agregan índices ni se afirma una mejora medida en el despliegue real.

## Reglas de selección preservadas

- El período comienza el día 21 y termina el día 20 del mes siguiente.
- Solo se facturan ODT Finalizadas y con aprobación efectiva, independientemente
  del filtro visual de revisión. Sin revisión y POR_REVISAR mantienen la regla vigente.
- Se excluyen ODT ya facturadas y se conserva la restricción única por ODT.
- Servicio y monto editados prevalecen cuando no son nulos; un monto cero es válido.
- Se preservan filtros de contratistas, servicios, tipo de cliente, estado y búsqueda.
- Una selección explícita sin contratistas no se amplía a todos. El filtro de
  servicios vacío conserva su semántica anterior, sin introducir otra regla.
- Al reutilizar una facturación del mismo contratista/período, no se sobrescribe
  su requisición existente, incluso si se recibe otro número al confirmar.
- El cambio explícito de requisición continúa disponible en su operación separada.

## Confirmar exactamente lo revisado

Resumen y comprobación de la selección se construyen durante la misma lectura
de ODT pendientes. No se obtiene el total de una consulta y la comprobación de
otra, porque un cambio entre ambas permitiría confirmar un valor no mostrado.

El formulario incorpora una confirmación firmada, asociada al usuario y a los
filtros. Contiene una huella de los registros mostrados: identidad de ODT,
contratista, servicio y monto efectivos, fecha de finalización y cuenta. Al
confirmar, el caso de uso vuelve a consultar y bloquear las ODT y compara la huella
antes de crear período, cabeceras o items.

Si cambia una ODT, su aprobación, servicio, monto, cuenta, contratista o pertenencia
a la selección, se pide actualizar la previsualización. Cambiar una ODT por otra
con el mismo monto y contratista tampoco pasa la comprobación. Se verifica tanto
el usuario como los filtros; no basta con que la cantidad coincida.

La confirmación vence por defecto a los 30 minutos. El tiempo se puede configurar
con `SSTT_CONFIRMACION_FACTURACION_SEGUNDOS`. Una confirmación vencida, manipulada,
de otro usuario o ausente no guarda datos. Tras actualizar esta versión, un
formulario abierto con la versión anterior necesita recargar la previsualización.
Los errores de validación vuelven a mostrar una previsualización para revisión;
la confirmación no se reintenta automáticamente.

La firma usa el mecanismo estándar de Django y depende de la `SECRET_KEY` activa.
No reemplaza permisos, CSRF ni la validación transaccional del servidor. Esta
entrega no cambia claves ni la configuración de seguridad del despliegue.

## Transacción y permisos

El caso de uso comprueba usuario activo, permiso y restricción de coordinadores
sin depender solo de los decoradores de la vista. Confirmar bloquea las ODT en
orden estable, vuelve a validar la selección, crea o reutiliza el período y las
cabeceras, y guarda los valores facturados como instantánea.

Si falla una inserción, se revierten los items, cabeceras y período creados dentro
de la operación. Repetir una confirmación no duplica items ni sobrescribe valores
ya facturados. Se preservan los autores de creación y las restricciones existentes.

El cambio de requisición tiene su propia transacción y bloqueo. Se mantienen las
reglas de número opcional y máximo 100 caracteres, y la redirección al historial.
No se incorpora un nuevo historial de cambios de requisición en esta entrega.

En motores que soportan bloqueo por fila, la consulta de confirmación limita el
bloqueo a las ODT para no intentar bloquear relaciones opcionales del join.
SQLite no adquiere bloqueos por fila: este cambio no certifica su concurrencia ni
elimina los posibles errores de bloqueo entre escritores.

## Validación

Las pruebas cubren permisos directos/HTTP, CSRF, períodos, límites de fecha,
aprobación efectiva, servicio corregido, monto cero, confirmaciones ausentes,
vencidas o manipuladas, cambio de usuario/filtros, cambio de ODT sin alterar la
cantidad, reutilización de requisiciones y rollback después de insertar un item.

La suite también prueba GET de previsualización seguido de POST de confirmación,
redirecciones del historial y actualización separada de requisición.

## Alcance del despliegue

Sin modelos, migraciones, dependencias ni cambios de CSS/JS. Se agrega únicamente
un campo oculto al formulario de confirmación. Las rutas y los mensajes principales
se conservan. No se ha modificado ningún servidor ni se ha probado con datos reales.

La anulación auditable de facturación es una etapa distinta y no se implementa
aquí. La protección del repositorio y la verificación de respaldos permanecen
pendientes para la etapa final acordada; esta extracción no realiza esas acciones.
