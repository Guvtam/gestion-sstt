# Paginación y preparación de filas

La vista conserva el control de permisos y el queryset autorizado.
No se vuelve a seleccionar el conjunto global de ODT al paginar.

| Módulo | Responsabilidad |
|---|---|
| consultas/filas_bandeja.py | Página de 50 IDs, carga ordenada de filas y datos complementarios por lote |
| presentacion/filas_bandeja.py | Atributos de presentación con los datos precargados |
| vistas/bandeja.py | Alcance del usuario, resolución de coordinadores, permisos y render |

El orden se conserva: cuenta, código técnico, finalización y número descendente.
Se usa get_page, manteniendo el tratamiento de números inválidos o fuera de rango.
Las relaciones de revisión y seguimiento se cargan con las filas.
El catálogo de cuentas y la pertenencia a facturación se leen por lote.

La preparación conserva las etiquetas de corrección, posibilidad de procesar,
nombre y disponibilidad del coordinador, bloqueo por rechazo o facturación,
CECO, clasificación y existencia de cuenta en catálogo. Recibe indicadores de
permiso explícitos; no consulta permisos ni realiza operaciones de escritura.

Los atributos visuales no sustituyen los permisos de las acciones POST.
La resolución de coordinadores y la asignación manual conservan sus reglas.

## Validación y límites

361 pruebas correctas. Nuevas regresiones verifican orden, máximo de 50,
alcance limitado, página vacía, número inválido, bloqueos, monto cero,
clasificación y verificación no disponible.

Con los datos aislados de prueba, la paginación y el último preventivo consumen
cuatro consultas, tanto con una fila como con 50. Los complementos consumen dos.
Preparar las filas ya cargadas ejecuta cero consultas.
Estos presupuestos excluyen autorización, indicadores y resolución de
coordinadores; no son una medición de la petición completa ni de carga real.

No cambia modelos, migraciones, plantillas ni estáticos.
No requiere migraciones o sincronizaciones adicionales.
No se accedió al despliegue ni se modificaron sus datos.
Persisten tareas de catálogos auxiliares, exportación PDF y componentes visuales.
