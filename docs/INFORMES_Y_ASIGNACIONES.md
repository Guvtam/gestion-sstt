# Casos de uso de informes y asignaciones

## Organización

Las rutas de actualizar informe y asignar coordinador delegan en
`casos_uso/informes_asignaciones.py`. Las vistas reciben los parámetros y devuelven
JSON; no guardan las entidades ni los eventos directamente.

La autorización general se comparte mediante `casos_uso/autorizacion.py`.
El bloqueo de ODT editables se comparte con edición y revisión en
`casos_uso/bloqueos_odt.py`, para mantener una sola comprobación de facturación y
rechazo dentro de la transacción.

## Informe técnico

- Exige usuario activo y el permiso de cambiar informe también cuando se invoca
  el caso de uso sin pasar por la vista.
- Un coordinador solo puede cambiar informes de sus ODT identificadas. El caso
  de uso compara el usuario conectado con el responsable verificado, sin aceptar
  responsables enviados desde los parámetros del formulario.
- La vista reutiliza la verificación de la misma petición realizada por el
  middleware. Otros consumidores pueden usar el verificador predeterminado.
- Una verificación fallida o una respuesta malformada impide guardar; no equivale
  a Sin identificar. El usuario sin vínculo de coordinador se rechaza antes de
  consultar el origen.
- Conserva los estados No enviado, Enviado y No aplica, y el bloqueo de ODT
  facturadas o rechazadas, incluso cuando se solicita el mismo estado.
- Estado de informe, autor, fecha y evento se guardan en una sola transacción.
  Un fallo del evento revierte también los campos del informe.
- Un envío repetido sin cambios no modifica autor/fecha ni duplica eventos.
- No se modifica el estado de pago. El evento usa su estado efectivo vigente,
  manteniendo la equivalencia de POR_REVISAR con Aprobada para el historial.

## Asignación manual

Se conserva la regla vigente de los dos usuarios autorizados por nombre, incluida
la exigencia de que estén activos. Ser superusuario con otro nombre no agrega
permiso para esta operación. No se crean permisos ni grupos nuevos.

La asignación solo se permite cuando no hay asignación local y una lectura válida
del origen informa que no hay coordinador identificado. Un fallo, una respuesta
vacía inesperada o un indicador de identificación de tipo incorrecto no habilitan
la asignación.

Se revisa la existencia local, se verifica el origen fuera de la transacción de
escritura y luego se bloquea/revalida la ODT local antes de crear la asignación y
su evento. Si aparece una asignación local durante esa verificación, se conserva
y se devuelve conflicto. Repetir la operación no la reasigna ni duplica el evento.

La asignación y su auditoría se confirman juntas. Si falla la auditoría, se revierte
la asignación. La prioridad de la asignación local en consultas posteriores se
mantiene.

Esta operación modifica responsabilidad, no servicio, monto, informe o estado de
pago. No agrega un bloqueo nuevo por facturación o rechazo: la regla anterior
permitía completar esa metadata si la ODT seguía sin responsable identificado.
Las instantáneas facturadas y las decisiones de pago no se alteran.

## Contratos HTTP

Se mantienen rutas, POST, sesión, CSRF, respuestas exitosas y mensajes de Sin cambios.
Los adaptadores comparten traducción de errores de aplicación:

| Situación | Respuesta |
|---|---|
| Entrada inválida | 400 |
| ODT inexistente | 404 |
| ODT bloqueada o asignación existente | 409 |
| No se pudo verificar responsable | 503 |
| Falta de permiso o responsable ajeno | 403 |

El middleware usa el mismo validador de número de ODT que los casos de uso. Un
número inválido de un coordinador se devuelve como 400 antes de consultar el
origen, en lugar de confundirse con un fallo de verificación.

Los verificadores inyectables son dependencias internas para reutilizar la
petición o realizar pruebas. No se seleccionan a partir de parámetros HTTP y no
eliminan la comprobación de usuario, permiso y coincidencia de responsable.

## Validación y límites

Se prueban estados, autor/fecha, auditoría, idempotencia, reversión ante errores,
permisos desde HTTP y directamente desde los casos de uso, ODT ajenas/no
identificadas, respuestas de origen inválidas, conservación de asignaciones
existentes y revalidación de cambios locales durante la lectura del origen.
También se prueba que middleware y caso de uso reutilicen una única consulta de
responsable en la petición de informe.

No hay transacción distribuida que congele el historial del origen. La lectura
del responsable representa el momento de verificación; no se promete impedir
que otro sistema cambie después. SQLite continúa sin bloqueo por fila y no se
certifica la concurrencia del despliegue con estas pruebas.

Sin modelos, migraciones, dependencias, estáticos ni cambios de configuración.
No se ha modificado el despliegue ni se ha usado el origen real. Las acciones de
protección de datos y verificación de respaldos continúan para la etapa final.
