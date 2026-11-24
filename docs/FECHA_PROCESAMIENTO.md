# Fecha de procesamiento en Seguimiento de cambios

La tabla original de Seguimiento de cambios agrega Fecha de procesamiento junto
a Última detección SoftGuard. Corresponde a la última fecha de EventoCorreccionODT
con estado_nuevo EN_PROCESO (etiqueta visible Procesada). Se presenta con segundos
en America/Santiago. Se consulta en un único agregado para las ODT de la página,
no una consulta por fila.

No se usa gestionado_en: también cambia cuando se marca Pendiente. No se usa la
fecha de detección SoftGuard, actualización automática ni fecha de solicitud.
Si se procesó varias veces se muestra la última; se conserva visible cuando
pasa a Actualizada o vuelve a Pendiente. Es un dato histórico de último
procesamiento, no indica que una nueva solicitud posterior ya esté procesada.
Sin evento verificable se muestra Sin registro, incluso si el estado actual
legacy es Procesada. No se inventan ni sobrescriben fechas.

Solo lectura: no cambia estados, permisos, sincronización, montos, facturas ni
reglas de conciliación. No requiere migración nueva; utiliza auditoría existente.
Actualizar main y reiniciar sstt-prueba tras integrar el PR. Debe estar aplicada
la migración 0016 de detecciones si se actualiza desde una versión anterior al
PR98. En ese caso seguir primero docs/DETECCIONES_SOFTGUARD.md.
