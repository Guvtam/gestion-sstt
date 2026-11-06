# Historial de requisiciones

Cada cambio real de número guarda el valor anterior, el nuevo, el usuario y la fecha.
También se registra la primera requisición si la facturación se crea con un número.
Dejarla pendiente es un cambio; guardar el mismo valor no genera otro evento.
La requisición y su evento se escriben en una misma transacción.

Desde los contratistas de un período, «Ver historial de requisición» permite consultar
los cambios, con 50 eventos por página. Se requiere el permiso operativo de exportación
de pagos; los coordinadores no obtienen acceso por tener ese permiso asignado.

La migración 0012 crea la tabla del historial. Antes de iniciar la aplicación
actualizada, ejecutar las migraciones con la configuración activa del entorno:

    python manage.py migrate --settings=CONFIGURACION_ACTIVA

No se reconstruyen cambios anteriores a esta función. Una facturación antigua
muestra un historial vacío hasta que se cambie su requisición.

Los eventos guardan una copia del identificador, contratista, período y nombre de
usuario. Si se elimina una cabecera o un usuario, el evento conserva esos datos.
El enlace directo del historial sigue funcionando tras eliminar la cabecera.
La administración permite consultar los eventos, pero no crearlos, editarlos ni
eliminarlos. Esto no impide modificaciones directas por un administrador de la
base de datos y no sustituye los respaldos.

Esta mejora conserva el comportamiento existente de eliminación de períodos:
no lo convierte en anulación contable.
