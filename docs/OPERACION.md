# Operación y transición del piloto

## Separar código, configuración y datos

- Git distribuye código y migraciones.
- El módulo local `config.settings_prueba` y el entorno del servicio determinan
  la configuración efectiva. No asumir que coincide con `config.settings`.
- La base de la Raspberry conserva usuarios, revisiones, correcciones,
  facturaciones, catálogos y equivalencias creados durante el piloto.
- Los logs y respaldos deben estar fuera del repositorio y tener acceso limitado.

La primera entrega de revisión no cambia el módulo del servicio, Nginx, SQLite,
el timer ni los datos. No activar una nueva configuración de producción sin
comprobar rutas, hosts, estáticos, sesiones, origen SQL y destino de base.

## Exposición actual en GitHub

El repositorio revisado es público y contiene archivos de configuración y datos.
Antes de publicar más datos:

1. Cambiar la visibilidad desde GitHub a privada si la política de la empresa
   lo permite. Esto no revoca copias ya descargadas.
2. Revisar qué secretos reales se publicaron y rotarlos en sus sistemas de origen;
   no pegar contraseñas en issues, PR, logs ni chats.
3. Respaldar cada base y configuración válida fuera de Git, en PC y Raspberry.
4. Retirar del seguimiento los datos/secretos en una rama específica y verificar
   cómo afectará el siguiente pull en cada equipo. Un archivo eliminado del
   repositorio puede desaparecer de la copia de trabajo al actualizar.
5. Si se requiere purgar el historial, coordinar la reescritura y renovación de
   clones con todos los colaboradores. Una eliminación en main no borra commits
   antiguos, ramas ni copias existentes. No reescribir historial durante el piloto
   sin una ventana y respaldos verificados.

`.gitignore` solo previene nuevos archivos sin seguimiento. No protege archivos
ya versionados y no constituye una remediación de la exposición existente.

## Antes de un release

En una copia separada y sin datos reales:

```bash
python -m pip install -r requirements-dev.txt
python manage.py check --settings=config.settings_test
python manage.py makemigrations --check --dry-run --settings=config.settings_test
python manage.py test contratistas revisiones --settings=config.settings_test
```

Registrar commit, versiones instaladas, comprobaciones y cambios de esquema.
Antes de ejecutar cualquier `migrate` en el piloto, revisar `migrate --plan` con
la configuración activa y disponer de un respaldo recuperable.

Para validar el despliegue real, ejecutar en el servidor `check --deploy` con
el módulo que utiliza Gunicorn. Revisar los resultados según acceso HTTP/HTTPS,
red y proxy efectivos; no activar redirección HTTPS hasta disponer de TLS real.
No usar los resultados de `settings_test` como certificado de producción.

## Respaldos recuperables

Para SQLite, usar su API de backup o detener todas las escrituras antes de copiar.
Copiar solo el archivo principal mientras hay escrituras/WAL puede generar un
respaldo inconsistente. Tener en cuenta tanto Gunicorn como sincronización y
comandos manuales. No incluir contraseñas en nombres de archivo o línea de comando.

Conservar copia local y copia en otro dispositivo con acceso restringido;
definir frecuencia y retención según pérdida máxima tolerable. El respaldo debe
incluir configuración necesaria y archivos subidos, si existen, además de la base.

En un entorno aislado, restaurar y comprobar:

- Integridad de SQLite y migraciones aplicadas.
- Cantidades de ODT, revisiones, eventos, correcciones, asignaciones y contratistas.
- Períodos, facturaciones, requisiciones, items y sumas de montos facturados.
- Grupos, permisos, sesiones nuevas y alcance de coordinadores.
- Lectura de PDF e historial; equivalencias y B2B/B2C/CECO.

Un mensaje de copia exitosa no demuestra que se pueda recuperar el sistema.

## Actualización controlada

1. Respaldar y verificar destino de la base y configuración activa.
2. Registrar commit actual y confirmar que no hay cambios locales de código
   que el pull pudiera pisar. No hacer `git reset --hard` ni restaurar una base.
3. Traer únicamente la versión revisada mediante avance directo.
4. Instalar dependencias necesarias dentro del entorno virtual.
5. Aplicar migraciones revisadas si ese release las incluye.
6. Recoger estáticos si cambiaron y conservar el esquema actual de Nginx.
7. Reiniciar servicio y verificar login, bandeja, detalle, exportación y permisos.
8. Registrar resultado y comprobar próxima sincronización.

La primera entrega de revisión no añade migraciones ni cambia estáticos. Las
pruebas son para la copia de desarrollo/CI; no cargar fixtures de prueba en la
base del piloto.

## Sincronización y registros

Comprobar en la Raspberry `sstt-sync.timer` y el resultado de `sstt-sync.service`.
Un timer cada 30 minutos solo vuelve a consultar el DW; si DW se carga una vez al
día, no crea información más reciente que esa carga. Registrar por separado
última carga del origen y última sincronización local completa.

La implementación actual actualiza por fila y puede quedar parcial ante fallo.
Se propone registrar inicio/fin, estado, filas creadas/actualizadas/omitidas,
fecha de origen, error resumido y duración. Incorporar exclusión de ejecuciones
simultáneas, también para comandos manuales. No registrar credenciales, datos
bancarios ni observaciones completas en logs técnicos.

## Traslado al servidor corporativo

1. Ensayar con una copia y acordar motor de base, rutas, TLS y usuario de servicio.
2. Instalar el mismo release y migraciones en destino vacío.
3. Transferir datos de la base SSTT completa; una nueva sincronización SoftGuard
   no reconstruye revisiones, facturaciones o equivalencias locales.
4. Si cambia el motor, preservar PK/FK, usuarios, permisos, decimales, fechas,
   secuencias y relaciones. No copiar un archivo SQLite sobre PostgreSQL.
5. Conciliar cantidades y totales; validar permisos y concurrencia con usuarios.
6. En la ventana de corte, detener escrituras y sincronización en la Raspberry,
   hacer respaldo final y repetir transferencia validada.
7. Activar destino; conservar Raspberry sin escrituras como recuperación temporal.
   No permitir que ambos sistemas registren pagos independientes.

Definir rollback antes del corte: después de escribir en destino, volver a la
base anterior sin reconciliar perdería cambios. La retirada del piloto se decide
tras aceptación funcional y verificación de respaldo/restauración en destino.
