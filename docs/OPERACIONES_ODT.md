# Casos de uso de edición y revisión de ODT

## Separación de responsabilidades

Las vistas `guardar_fila`, `actualizar_revision` y `acciones` validan el transporte
HTTP, delegan la operación y convierten su resultado en JSON o redirección HTML.
No guardan directamente ODT o revisiones. Se conservan sus URLs, métodos POST,
decoradores de sesión/permisos y protección CSRF.

`casos_uso/edicion_odt.py` contiene tres operaciones independientes de HTTP:

| Caso de uso | Responsabilidad |
|---|---|
| `editar_odt` | Guardar diferencias de servicio/monto y sus eventos |
| `revisar_odt` | Cambiar el estado de pago de una ODT y registrar el motivo |
| `revisar_odts` | Revisar una selección de ODT en una sola transacción |

Los casos de uso exigen un usuario activo con el permiso correspondiente. La
restricción de coordinadores también se aplica en esta capa, para que un futuro
consumidor interno no pueda saltársela omitiendo el middleware. Revisar pagos no
otorga el permiso de editar servicio o monto.

Los errores de validación, bloqueo e inexistencia son independientes de HTTP.
El adaptador JSON los convierte en 400, 409 y 404 respectivamente. La revisión
múltiple conserva su redirección y mensajes HTML. Los errores inesperados de base
o auditoría no se convierten en respuestas de éxito.

## Reglas preservadas

- Las ODT facturadas o rechazadas definitivamente no permiten edición/revisión.
- Ausencia de revisión y POR_REVISAR siguen siendo aprobación efectiva por la
  regla vigente; no se cambia esa decisión de negocio.
- En revisión o Rechazado requieren motivo. En revisión puede volver a Aprobado;
  el rechazo definitivo no puede revertirse desde estas operaciones.
- Editar servicio/monto no modifica el estado de pago. El parámetro legado de
  estado del formulario conserva su validación, pero no se usa para revisarlo.
- El monto debe ser finito, no negativo y tener como máximo dos decimales. Un
  cambio requiere confirmación explícita; el valor cero no se trata como vacío.
- Un nuevo servicio debe pertenecer a los cuatro principales. Un servicio histórico
  puede conservarse sin obligar a reemplazarlo para corregir solo el monto.
- Se guardan diferencias con el origen. Volver a los valores originales limpia
  las ediciones y la marca manual; no se modifican los campos originales.
- Las operaciones sin cambio no crean revisiones, seguimientos ni eventos nuevos.
- El seguimiento de corrección y los eventos se guardan en la misma transacción
  que la edición. Si falla la auditoría, revierte toda la operación.

La comprobación de bloqueo es común al resto de consumidores mediante
`consultas/pagos.py`; su mensaje se define en el dominio. Se conservan los imports
anteriores desde vistas para consumidores existentes.

## Revisión múltiple

Se deduplican los números y se admite un máximo de 300 ODT distintas. Se cargan
las ODT en orden estable, junto con revisiones y referencias de facturación.
Se comprueba que todas existan y sean editables antes de guardar la primera.
Un fallo al guardar cualquier revisión o evento revierte la selección completa.

La validación ya no descarta silenciosamente números inválidos para procesar
solo el resto. Una selección mezclada con un número inválido falla completa.

## Números de ODT

La revisión individual admite número simple o formato de miles con espacios o
puntos, como `77527`, `77 527` y `77.527`. No extrae dígitos de texto arbitrario,
signos u otros separadores: una entrada como `77x527` se rechaza en lugar de
interpretarse como otra selección. Se limita longitud y rango antes de consultar.
Esta es una mejora deliberada respecto de la extracción anterior de dígitos.

## Transacciones y límites

Se mantiene `transaction.atomic()` y `select_for_update()`, con comprobación de
bloqueo dentro de la transacción. Esto no agrega bloqueos por fila a SQLite ni
resuelve su concurrencia con otros escritores. La seguridad transaccional ante
fallos se prueba; la carga concurrente del despliegue real sigue pendiente.

Las vistas de informe, asignación, catálogo y facturación no se reestructuran en
esta entrega. Los accesos directos del administrador o futuros consumidores deben
evaluarse por separado; no se afirma que todos los caminos de escritura del
sistema ya estén centralizados.

## Validación y despliegue

Las pruebas cubren permisos tanto desde HTTP como desde los casos de uso,
separación entre edición y revisión, rechazo definitivo, bloqueo por facturación,
montos cero/NaN/negativos/precisión, confirmación, servicios históricos, auditoría,
idempotencia, rollback individual y múltiple, selección inválida y CSRF.

No se modifican modelos, tablas, dependencias, estáticos ni rutas. Esta entrega
no genera una migración nueva. Las migraciones pendientes de versiones anteriores
deben revisarse con la configuración activa antes de actualizar el despliegue.
