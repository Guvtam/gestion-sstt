# Revisión de usuarios y permisos

## Inventario local

Desde la carpeta del proyecto y el entorno virtual:

```bash
python manage.py diagnosticar_usuarios
python manage.py diagnosticar_usuarios --usuario NOMBRE_USUARIO
python manage.py diagnosticar_usuarios --json
```

Si la instalación utiliza otro módulo de configuración, agregar
`--settings=PAQUETE.MODULO_CONFIGURACION` con el mismo módulo que usa el servicio.
El diagnóstico solo lee la base local. No consulta SQL Server, inicia sesiones,
cambia permisos ni imprime contraseñas, correos o datos bancarios.

El resultado muestra grupos, permisos Django, perfil de coordinador, identidad
SoftGuard y vínculo explícito (si existe). Incluye usuarios inactivos. No deduce
un rol de negocio a partir de `is_staff`: este indicador permite entrar en la
administración cuando corresponda, pero no concede los permisos SSTT.

Los permisos enumerados son los que devuelve el sistema de autenticación Django.
No constituyen una promesa de acceso: el middleware y los casos de uso también
restringen las páginas y el alcance de coordinador. Un vínculo inactivo no libera
esas restricciones. Los superusuarios y las excepciones de administrador definidas
en el sistema deben revisarse por separado. El informe no verifica la pertenencia
de ninguna ODT ni la conectividad al origen.

## Validación funcional pendiente en cada instalación

Usar sesiones separadas para cada perfil y ODT de prueba identificadas previamente.
No modificar pagos ni facturar órdenes reales para comprobar acceso.

| Perfil o condición | Verificación |
| --- | --- |
| Sin sesión | La bandeja requiere iniciar sesión. |
| Activo sin permiso de bandeja | No puede abrir la bandeja ni consultar sus opciones AJAX. |
| Staff sin permisos SSTT | No obtiene acceso operativo por ser staff. |
| Coordinador vinculado | La bandeja muestra solo sus ODT, incluso manipulando el filtro de coordinador. |
| Coordinador con vínculo inactivo | El acceso operativo queda bloqueado. |
| Coordinador | Accede a bandeja y calendario de sus ODT; no accede a otras páginas ni a operaciones financieras, aunque reciba permisos adicionales. |
| Coordinador: calendario y selector de servicios | Solo muestra visitas y opciones de sus ODT; no muestra órdenes ajenas ni sin responsable identificado. |
| Coordinador: historial, informe y correcciones | Solo funcionan sobre sus ODT identificadas y con el permiso correspondiente. |
| Sin responsable verificable | No se autoriza una ODT por fallo de SQL Server. |
| Revisor o administrador | Cada acción requiere su permiso; tener uno no concede los demás. |
| Exportación sin permiso bancario | El PDF no muestra datos bancarios. |
| Usuario inactivo | No puede iniciar sesión. |

Las pruebas automáticas cubren estas restricciones mediante datos aislados y
simulación del origen. La revisión con los usuarios, grupos y conexiones reales
sigue siendo necesaria: el repositorio no contiene las bases de cada instalación.

No otorgar permisos automáticamente para eliminar avisos. Revisar primero el
rol esperado de cada persona; conservar los permisos mínimos para su función.
