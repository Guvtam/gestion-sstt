# Gestión de correcciones separada de HTTP

casos_uso/gestion_correcciones.gestionar_correccion concentra autorización,
alcance, validación y escritura. La vista mantiene login, POST y adaptación
de errores a HTTP. Dominio define el resultado y los estados manuales admitidos.

Se conserva EN_PROCESO como valor interno de «Procesada».
Un coordinador solo puede marcar ese estado y debe tener alcance sobre la ODT.
Un usuario operativo requiere permiso de edición. El usuario debe estar activo.
El caso comprueba estas reglas incluso si se invoca sin la vista.

La verificación del alcance por defecto utiliza la política compartida. La vista
puede aportar su verificador de petición para reutilizar datos ya cargados.
Un fallo no se convierte en autorización ni expone la excepción del origen.

La actualización y su evento se escriben dentro de la misma transacción.
Una petición repetida con el mismo estado no duplica el evento de gestión.
Si se crea seguimiento para una modificación antigua, su evento inicial
también queda dentro de la transacción. Los errores posteriores lo revierten.

## Ajustes de integridad explícitos

Se reutiliza la validación común del número: admite números normales y el
formato agrupado, pero rechaza prefijos, signos y caracteres arbitrarios.
Antes se extraían silenciosamente los dígitos de entradas malformadas.
La entrada inválida responde 400 sin cambiar la ODT.

Un intento rechazado por coincidencia con SoftGuard no deja un seguimiento
nuevo ni su evento confirmados. Antes el retorno 409 dentro de atomic podía
confirmar esas escrituras preliminares. El rechazo ahora revierte el intento.

ACTUALIZADA no es un estado manual. La coincidencia con el origen conserva su
política en sincronización. No se cambian servicios, montos ni facturación.

## Validación y aplicación

410 pruebas correctas; check y comprobación de migraciones sin incidencias.
Nuevas regresiones: autor/fecha/evento, idempotencia, rol y alcance, origen caído,
invocación directa, usuario inactivo, rollback de estado y seguimiento nuevo,
coincidencia, entrada numérica, ODT ausente y monto cero.

Sin nuevas migraciones, estáticos o sincronización adicional.
No se modificaron datos del despliegue ni se probó el servidor.
Se conservan las limitaciones de bloqueo por fila de SQLite.
