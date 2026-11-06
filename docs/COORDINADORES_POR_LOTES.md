# Identificación de coordinadores por lotes

## Qué cambia

La bandeja, los filtros de coordinador, los contratistas disponibles, las ODT
modificadas y las estadísticas de correcciones dejan de identificar responsables
mediante una consulta independiente por cada ODT. Comparten una resolución por
lotes de hasta 250 números y reutilizan los resultados dentro de una petición.

Cada lote hace una consulta local de asignaciones manuales. Si faltan responsables,
hace una consulta al origen para esas ODT, pidiendo solo número, fecha, acción e
identificador de usuario. No descarga observaciones, imágenes, nombres o correos
del historial. Las listas de números y usuarios se parametrizan.

El endpoint de contratistas aplica fecha, estado y servicios antes de resolver
el alcance del coordinador. La autorización se sigue aplicando antes de devolver
cualquier contratista. Así no se identifican innecesariamente todas las ODT
cuando la petición ya está acotada por período.

## Regla compartida

`dominio/coordinadores.py` contiene la misma inferencia para consulta individual
y por lotes, sin acceso a la base de datos:

- Se consideran solo acciones de los coordinadores configurados.
- Una asignación manual local válida prevalece sobre el historial del origen.
- Entre eventos con fecha, se prioriza la última acción autorizada.
- Si la última fecha empata entre diferentes responsables, no se atribuye uno.
- Cuando todos los eventos carecen de fecha, solo se identifica si apuntan al
  mismo usuario autorizado.
- Sin eventos atribuibles tras una lectura exitosa, queda Sin identificar.

No se agregan ni modifican coordinadores o permisos. Las consultas individuales
existentes conservan su interfaz y comparten la regla de inferencia; la verificación
previa a una asignación manual continúa usando la consulta individual del origen.

## Caché y autorización

`coordinadores_en_peticion` guarda datos de responsable, no resultados booleanos
de permiso. El usuario conectado se compara con esos datos al aplicar el alcance.
No existe caché global ni persistente: una nueva petición vuelve a verificar el
origen cuando no hay asignación manual local.

Los coordinadores siguen viendo solo sus ODT identificadas. Cambiar el filtro de
la URL no amplía su alcance, y las ODT sin identificar siguen excluidas.

Si falla una consulta necesaria para autorizar o filtrar, se devuelve 503. No se
devuelve una selección parcial aunque ya se hayan resuelto lotes anteriores.
Un error del origen o una asignación local inválida no se transforman en Sin
identificar, ni se almacenan como una respuesta negativa válida.

La presentación tiene un fallback separado: un usuario que ya puede ver las ODT
sin filtrarlas por responsable puede ver No disponible cuando falla el origen.
Las asignaciones manuales verificadas se conservan para mostrar. Los registros
no verificados no habilitan la asignación manual desde esa pantalla. Este fallback
no se usa para autorización ni para filtrar Sin identificar.

Las estadísticas que requieren responsables completos también responden 503 si
falla una verificación, en lugar de agrupar los fallos como Sin identificar.
Los errores del driver no se incluyen en la respuesta pública.

## Validación

Se cubren prioridad manual, última acción, empates, falta de fechas, lectura vacía,
parametrización, límites de lote, reutilización en una petición y separación entre
peticiones. Se prueban permisos reales de coordinador con filtros manipulados,
fallos de origen, fallo del segundo lote y distinción entre no identificado y
no disponible, además de las pantallas y operaciones existentes.

La prueba de presupuesto usa 250 ODT sin asignación manual: una consulta local
y una llamada agrupada al origen. Para 501 números se hacen tres lotes; volver a
pedir datos ya resueltos dentro de la misma petición no agrega consultas.

## Límites y despliegue

No se crean modelos, migraciones, estáticos ni dependencias. No se cambia la
configuración del despliegue ni se ejecutan consultas contra el origen real
durante estas pruebas.

Esta mejora reduce viajes al origen, pero no elimina la dependencia de SQL para
las ODT sin asignación manual. Una proyección local persistente necesita definir
frescura, revalidación y comportamiento ante cambios de responsable; no se
introduce una atribución antigua como autorización implícita en esta entrega.

Los lotes acotan la cantidad de ODT por consulta, no el número total de eventos
de cada ODT. Una selección muy amplia todavía requiere trabajo y memoria
proporcionales a sus candidatos y eventos. Falta medir latencia y memoria en el
despliegue real; no se afirma una mejora de segundos sin esa medición.
