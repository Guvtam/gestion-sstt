# Usuarios vinculados a coordinadores

En Administración de Django, «Vínculos de coordinadores» permite asociar un
usuario local con uno de los responsables SoftGuard ya reconocidos por el
sistema. El login puede ser distinto de la identidad de origen.

Requiere la migración 0013 antes de iniciar la nueva versión. Ejecutar migrate
con la configuración activa del entorno. La migración solo crea la tabla:
no modifica usuarios, grupos, permisos ni asignaciones de ODT existentes.

## Configuración

1. Ingresar con una cuenta administrativa con permiso sobre este modelo.
2. Crear o seleccionar el usuario local.
3. Seleccionar el responsable SoftGuard y guardar el vínculo activo.
4. Mantener los permisos de bandeja y sus operaciones autorizadas para ese usuario.
5. Comprobar que solo ve sus ODT.

El vínculo identifica al coordinador; no concede permisos de edición, exportación
ni administración. Los permisos operativos adicionales siguen rechazados para
coordinadores aunque se les hayan asignado por error.

Cada usuario tiene como máximo un vínculo y cada identidad de origen tiene
como máximo un vínculo, incluso si está inactivo. Para sustituir un login,
modificar el usuario del vínculo existente. Antes se debe desactivar la cuenta
histórica que conservaría acceso por nombre; el formulario comprueba ese caso.

## Desactivar y compatibilidad

Desactivar el vínculo bloquea el acceso del coordinador. No recupera el acceso
histórico por coincidencia de nombre ni lo convierte en un usuario sin
restricciones. El administrador no permite borrar vínculos; permite desactivarlos.

Las cuentas históricas sin vínculo continúan con el comportamiento anterior,
para evitar interrumpir el piloto al ejecutar la migración.
Un vínculo explícito tiene prioridad sobre la coincidencia de nombre.
Una identidad inválida no autoriza acceso.

Los datos del vínculo se reutilizan solo en la instancia de usuario de la
petición; una petición nueva consulta el estado actual. No existe caché global.

## Límites y próximos pasos

Esta entrega configura la relación entre login e identidades de origen ya
conocidas. El catálogo de esas identidades todavía está en código: incorporar
nuevos responsables SoftGuard sigue pendiente. Se conservan las excepciones
administrativas autorizadas y la prioridad de asignaciones manuales de ODT.

La proyección local persistente de responsables de ODT no se implementa aquí.
La resolución de ODT mantiene las consultas por lotes y su denegación ante fallo
del origen. No se modifican sincronización ni configuración del servidor.

Validación: 319 pruebas correctas, incluidas nuevas regresiones de vínculo
activo/inactivo, compatibilidad, aislamiento, permisos y formulario administrativo.
Los cambios no se instalan automáticamente en el despliegue.
