# Actualización del catálogo como caso de uso

guardar_cuenta es ahora un adaptador de POST, mensajes y errores.
casos_uso/cuentas.actualizar_cuenta comprueba permisos y coordina la escritura.
dominio/administracion_cuentas contiene validación y contratos sin ORM ni HTTP.

Se conserva la selección explícita de B2B, B2C o SIN_CLASIFICAR, CECO, observaciones,
marca de revisión y autor. La proyección de ODT sigue comparando el código de
cuenta normalizado y no altera servicios, montos ni decisiones financieras.

La proyección se escribe en lotes de hasta 500 dentro de una sola transacción.
No se acumulan todas las ODT modificadas en memoria. Una excepción en un lote
posterior revierte también el catálogo y los lotes anteriores.
El bloqueo por fila conserva las limitaciones ya conocidas de SQLite.

El caso de uso exige usuario activo, permiso de administrar cuentas y perfil
operativo permitido. Un coordinador no obtiene acceso por asignarle ese permiso.
Esto también se comprueba cuando el caso se invoca sin pasar por HTTP.

Se preservan redirección, mensaje de validación y 404 del adaptador.
No se incorpora auditoría histórica nueva ni cambia la regla de lectura B2C.
No requiere migraciones o sincronización adicional.

La suite incluye preservación de campos locales, cuenta renombrada, CECO vacío,
idempotencia, permisos y rollback después de un primer lote de 500.
No se ejecutó esta operación sobre datos del despliegue.
