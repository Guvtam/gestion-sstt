# Detección de cambios de servicio y monto en SoftGuard

Seguimiento de cambios muestra un historial independiente de cambios del origen:
ODT, campo, valor anterior, valor nuevo, variación de monto y fecha/hora en que
SSTT observó la diferencia durante una sincronización confirmada. Fecha almacenada
en UTC y presentada con segundos en America/Santiago. No es fecha de edición en
SoftGuard ni fecha de modificación general de la ODT.

La tabla nueva CambioSoftGuard se crea vacía con 0016_cambios_softguard. No se
inventan detecciones previas ni se rellenan fechas históricas a partir del estado
Actualizada. Las ODT nuevas son referencia inicial, no cambios. Se comparan solo
servicio y valor_pago_tecnico originales de ODT existentes antes de reemplazarlos;
los cambios manuales, ajustes locales y otros campos no generan estos eventos.
Cada campo modificado genera una fila. Repetir el mismo origen no genera otra.

Los eventos y las actualizaciones se confirman en la misma transacción del lote.
Una falla de auditoría revierte ese lote. Si una ejecución falla después, se
conservan eventos de lotes previamente confirmados, asociados a la ejecución que
refleja FALLIDA/INTERRUMPIDA. Esto no afirma que la sincronización completa haya
terminado correctamente. La simulación no escribe eventos. El bloqueo compartido
de sincronización, conteos, contratos de transformación y reglas de conciliación
se mantienen. No cambia bloqueo de períodos ni conciliación financiera diaria.

Los montos se conservan exactamente con dos decimales; el formato visual CLP usa
la convención entera existente. La marca local 2 no se registra como valor previo
de origen. Retirarla por coincidencia sigue auditándose en EventoCorreccionODT.
No se modifican instantáneas facturadas, informes, revisiones ni objetivos locales.

## Consulta

El bloque tiene filtros propios sg_desde/sg_hasta (día local inclusivo), sg_odt y
sg_campo; 50 filas por página, orden de detección descendente y desempate por PK.
Incluye ODT sin corrección manual. Los filtros superiores siguen aplicando solo
al seguimiento de correcciones; las fechas nuevas solo al historial de origen.
El listado original agrega Última detección SoftGuard; sin evento muestra Sin
registro. No se confunde con actualizada_en, que representa una confirmación de
corrección y puede tener otro origen.

El bloque de importes requiere permisos existentes ver_bandeja_sstt y
ver_montos_sstt, además del middleware de alcance actual. No se da acceso nuevo a
coordinadores ni a usuarios de calendario. No consulta SQL Server al abrir la
pantalla; lee las detecciones ya guardadas por la sincronización.

## Activación Raspberry (solo después de integrar el PR)

Nueva migración aditiva, no reemplazar ni restaurar la base por una copia local.
Antes de actualizar código, verificar estado Git y crear copia SQLite consistente
con la función de respaldo ya existente (verifica integrity_check y no sobrescribe):

```bash
cd /home/tamara/gestion-sstt-prueba
source .venv/bin/activate
git status
python manage.py shell --settings=config.settings_prueba -c 'from pathlib import Path; from django.utils import timezone; from revisiones.management.commands.reparar_contratistas_odt import respaldar_sqlite; print(respaldar_sqlite(Path("/home/tamara/sstt-datos-prueba") / ("antes_detecciones_" + timezone.now().strftime("%Y%m%d_%H%M%S") + ".sqlite3")))'
```

Si el respaldo o Git fallan, detenerse. En una ventana breve de mantenimiento,
con sincronización programada pausada hasta finalizar la migración:

```bash
sudo systemctl stop sstt-prueba
git pull --ff-only
python manage.py migrate --settings=config.settings_prueba
python manage.py check --settings=config.settings_prueba
python manage.py collectstatic --noinput --settings=config.settings_prueba
sudo cp -R /home/tamara/sstt-datos-prueba/static/. /var/www/sstt-prueba/static/
sudo systemctl start sstt-prueba
sudo systemctl is-active sstt-prueba
```

La tarea de sincronización debe reanudarse después de migrate exitoso. No asumir
un nombre de timer/cron: usar el programador ya configurado en el piloto. No
iniciar nueva sincronización con código nuevo antes de migrar. Si falla cualquier
paso, no continuar automáticamente; revisar salida antes de reanudar.

Luego Ctrl+F5, abrir Seguimiento de cambios. Inicialmente vacío; la siguiente
sincronización real guardará solo las diferencias efectivamente observadas.
La primera referencia es el valor ya guardado en cada ODT al activar la función.
Los pasos no ejecutan consultas de origen ni sincronizaciones desde esta sesión.
