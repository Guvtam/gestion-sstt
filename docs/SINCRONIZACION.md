# Sincronización por lotes y trazabilidad

## Contrato del proceso

El comando `sincronizar_odts` delega al caso de uso de sincronización. La lectura
del origen utiliza `fetchmany` y cierra cursor y conexión al terminar, fallar o
cerrar el generador. El tamaño predeterminado es 250 filas, configurable entre
1 y 1000. No se cargan todas las ODT ni todos los números locales en memoria.

Cada lote usa una transacción local: consulta el catálogo y las ODT del lote,
inserta nuevas, actualiza en bloque las que cambiaron y verifica objetivos de
corrección. Los contadores del historial se confirman en la misma transacción.
No se mantiene la transacción local abierta mientras se descarga el siguiente
lote. Las ODT sin cambios de origen no se reescriben, aunque puede actualizarse
su seguimiento de corrección. Las equivalencias automáticas se aplican al final,
en una transacción separada junto al cierre exitoso de la ejecución.

El contrato de transformación contiene solo campos de origen y clasificación
proyectada. No incluye servicio/monto editados, contratista existente, revisión,
informe, asignación manual de coordinador ni valores facturados. La sincronización
no elimina ODT cuando el origen deja de devolverlas.

## Historial

La migración `0011_ejecucionsincronizacion` crea una tabla nueva. No transforma
datos existentes de ODT o facturación ni reconstruye ejecuciones anteriores.

| Estado | Significado |
|---|---|
| En curso | Iniciada; si murió el proceso, puede estar pendiente de recuperación |
| Completada | Consulta, lotes y equivalencias terminaron sin omisiones detectadas |
| Completada con omisiones | Terminó, pero hubo números/fechas inválidos o números duplicados dentro de un lote |
| Fallida | Ocurrió un error; pueden existir lotes anteriores confirmados |
| Interrumpida | Interrupción capturada o ejecución huérfana recuperada en un intento posterior |

Se registran inicio/fin, duración, filas consultadas, creadas, actualizadas, sin
cambios, omitidas, cuentas incorporadas, equivalencias creadas y fecha de carga
más reciente observada. Las omisiones se cuentan, sin detalle por cada fila.
Los mensajes completos del driver y los registros del origen no se guardan;
el código de error contiene únicamente el tipo de excepción.

`consultadas` cuenta filas recibidas, incluidas las de un lote que quedara pendiente
al fallar la lectura. Los contadores de escritura corresponden a lotes confirmados;
un lote revertido no incrementa creadas o actualizadas. `sin_cambios` describe los
campos originales de la ODT, no necesariamente su seguimiento de corrección.

La fecha de carga es el máximo observado, no una garantía de que todas las filas
pertenezcan a la misma instantánea del origen. El último intento y la última
ejecución completa sin omisiones se informan por separado. Ejecutar más seguido
no vuelve más reciente un origen que todavía no se actualizó.

El comando advierte cuando termina con omisiones, pero devuelve un estado de
salida exitoso. La monitorización debe consultar el estado persistido, además
del código de salida. Esta entrega no agrega alertas automáticas.

## Exclusión de procesos

Se usa un bloqueo de archivo del sistema operativo, no un indicador con vencimiento.
Un segundo intento en el mismo host se rechaza antes de leer el origen o crear
historial. El sistema operativo libera el bloqueo al terminar el proceso. No
eliminar el archivo para forzar una ejecución: podría permitir dos bloqueos sobre
archivos distintos mientras un proceso anterior sigue activo.

Linux utiliza `flock`; Windows utiliza `msvcrt.locking`. La prueba entre procesos
se ejecutó en Linux. La ubicación puede configurarse con `SSTT_SYNC_LOCK_FILE`.
Todos los ejecutores de una misma instalación deben usar la misma ruta estable,
escribible por el usuario que ejecuta el proceso. No cambiarla durante una ejecución.

La ubicación predeterminada se deriva de la base SQLite. Para otros motores se
usa el directorio base del proyecto. Esto coordina procesos de un mismo host:
no implementa un bloqueo distribuido ni protege las escrituras web concurrentes
de SQLite. Antes de usar varios hosts se requiere coordinación adicional.

Una ejecución huérfana se recupera después de adquirir el bloqueo, en la siguiente
ejecución real. Su fecha de fin corresponde a la detección, no al instante exacto
de muerte del proceso. Si la base tampoco permite registrar un fallo, el historial
puede quedar En curso hasta esa recuperación.

## Comandos

Sustituir `CONFIGURACION_ACTIVA` por el módulo de configuración de la instalación,
manteniendo sus valores y ubicaciones fuera de la documentación pública.

```bash
python manage.py sincronizar_odts --settings=CONFIGURACION_ACTIVA
python manage.py estado_sincronizacion --settings=CONFIGURACION_ACTIVA
python manage.py sincronizar_odts --simular --settings=CONFIGURACION_ACTIVA
python manage.py sincronizar_odts --tamano-lote 100 --settings=CONFIGURACION_ACTIVA
```

La simulación no escribe ODT, catálogos, equivalencias ni historial, y no recupera
registros huérfanos. Sí abre el bloqueo de exclusión para evitar solaparse con una
ejecución real. El comando de estado consulta solo la base local. El historial
también se expone en la administración estándar del proyecto, con permisos de
consulta y sin acciones de agregar, modificar o eliminar registros.

## Aplicación de la versión

1. Preparar un respaldo verificable de la base y conservar la configuración activa.
2. Pausar los ejecutores automáticos y las escrituras durante la actualización.
3. Actualizar a la versión revisada del código.
4. Revisar el plan, aplicar migraciones y ejecutar las comprobaciones con la
   configuración activa de esa instalación.
5. Si todo termina correctamente, reanudar los procesos y revisar el estado.

```bash
python manage.py migrate --plan --settings=CONFIGURACION_ACTIVA
python manage.py migrate --settings=CONFIGURACION_ACTIVA
python manage.py check --settings=CONFIGURACION_ACTIVA
python manage.py estado_sincronizacion --settings=CONFIGURACION_ACTIVA
```

Antes de la primera sincronización con esta versión es normal no tener historial.
El comando existente conserva su nombre y tamaño predeterminado; no se requiere
cambiar su programación. Esta entrega no cambia dependencias ni archivos estáticos.

## Validación y límites

Se prueban lectura por lotes, cierre de recursos, bloqueo entre procesos, rollback
de lote, fallos parciales, interrupción, recuperación, simulación sin escrituras,
idempotencia, lotes de 1000 filas, conservación de decisiones locales y valores
facturados, y administración de solo lectura.

No se ejecutó contra el origen real ni se midió memoria o tiempo en el equipo de
despliegue. La lectura sigue recorriendo el origen completo en cada ejecución.
La sincronización incremental requiere un indicador de avance fiable y reglas
para cambios retroactivos. No se modifican la identificación de coordinadores,
la anulación de facturación ni la configuración de producción.
