# Contratista operativo actualizado desde SoftGuard

## Causa y regla corregida

Antes, al crear una ODT se copiaba `tecnico` a `contratista`, pero un valor local
no vacío nunca se actualizaba. Si inicialmente figuraba una coordinadora y después
SoftGuard asignaba un técnico externo, la tabla mostraba el técnico nuevo arriba
y el contratista antiguo debajo; el filtro y la facturación pendiente usaban el
nombre antiguo.

Ahora `ODT.contratista` es el espejo operativo del técnico no vacío de SoftGuard,
limitado a los 150 caracteres del campo. Se corrige en cada sincronización aunque
el técnico ya estuviera actualizado y solo faltara alinear contratista. El cambio
se confirma junto al lote y su auditoría. No existe un override manual independiente
de este campo: el origen válido prevalece. El catálogo de contratistas y sus
vinculaciones no se cambian.

Un técnico vacío no borra un contratista existente. Si SoftGuard sigue informando
un coordinador como técnico, el sistema no adivina a qué externo corresponde:
esa asignación debe corregirse en SoftGuard.

## Datos preservados

La reparación solo actualiza contratista y crea un evento con nombre anterior,
nuevo y origen. El evento se ve en el historial de la ODT. No cambia servicio,
monto editado, estado de pago, informe, coordinador ni objetivos de corrección.
La sincronización conserva sus reglas existentes para los demás campos.

Las facturas ya emitidas mantienen sus cabeceras (contratista y requisición) y
sus instantáneas de servicio/monto. Una factura emitida con un nombre incorrecto
requiere revisión separada; este cambio no reasigna documentos ni duplica ODT.
Las previsualizaciones pendientes se invalidan si cambió el contratista antes de
confirmar: se exige generarlas nuevamente con la selección corregida.

## Reparar diferencias existentes en la Raspberry

Después de integrar el PR y actualizar el código, con el entorno virtual activo:

```bash
python manage.py reparar_contratistas_odt --settings=config.settings_prueba
```

Sin `--aplicar` solo informa la cantidad y hasta 20 ejemplos. No consulta SQL Server;
utiliza el técnico de la última sincronización local y no modifica la base.

Para aplicar, el comando exige un respaldo SQLite nuevo, crea una copia consistente
con la API de backup de SQLite, comprueba `integrity_check` y solo entonces repara.
No sobrescribe un respaldo existente. El directorio debe existir.

```bash
python manage.py reparar_contratistas_odt --aplicar --respaldo /home/tamara/sstt-datos-prueba/antes_reparar_contratistas_20261123.sqlite3 --settings=config.settings_prueba
sudo systemctl restart sstt-prueba
sudo systemctl is-active sstt-prueba
```

La reparación comparte el bloqueo con la sincronización, revalida cada lote bajo
transacción y actualiza solo el campo contratista. Procesa lotes de 250, deja
trazabilidad y es idempotente. Si hay otra sincronización activa, finaliza sin
aplicar. No requiere migraciones. El respaldo automático de este comando está
implementado para SQLite, usado en el piloto.

Luego recargar con Ctrl+F5, pulsar Limpiar y seleccionar nuevamente el contratista.
Los enlaces antiguos que seleccionaban el nombre anterior no se transforman en
un filtro nuevo automáticamente.

Las pruebas automatizadas usan base aislada, origen simulado y respaldo SQLite
local de prueba; no modifican la Raspberry ni consultan SQL Server real.
