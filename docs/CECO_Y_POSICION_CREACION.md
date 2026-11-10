# CECO pendiente y edición en ODT por creación

La bandeja muestra «Asignar / revisar CECO» si no encuentra la cuenta en el
catálogo, si el CECO está vacío o contiene solo espacios, o si está marcado
para revisión. La consulta no crea cuentas ni modifica sus datos o banderas.
Los CECO conocidos y sin revisión pendiente siguen mostrándose normalmente.
El mismo texto sustituye los avisos de CECO vacío en preventivos, detalle de
facturación y documentos PDF. Los montos y las facturas guardadas no cambian.

Administración de cuentas añade un filtro CECO: Todos, Sin CECO asignado,
Con CECO asignado y Por asignar / revisar. Este último incluye códigos vacíos
o marcados para revisión. Se combina con búsqueda, clasificación y pendientes,
y se conserva al paginar. La búsqueda existente permite escribir un CECO concreto.
El indicador CECO por asignar / revisar utiliza esa misma condición.
El filtro consulta el catálogo existente; no inventa un código para cuentas
ausentes ni convierte una consulta de lectura en una sincronización.
La paginación numerada está disponible arriba y abajo del catálogo, con primera
página, anterior, siguiente y la página actual. En listados grandes utiliza una
ventana acotada de números; todos los enlaces mantienen los filtros.

ODT por creación utiliza el orden estable existente de cuenta, código técnico,
finalización y número, sin priorizar cambios de servicio, monto o estado de
corrección. Así guardar una fila no la traslada a la página uno. La restauración
compartida conserva filtros, página y desplazamiento vertical/horizontal.
Gestión de pagos mantiene su prioridad de correcciones y localización de la ODT
guardada, incluso cuando su posición cambia. Las consultas siguen respetando
los filtros y el alcance autorizado; si la ODT deja de cumplir los filtros no se
fuerza su inclusión.

No requiere migraciones ni sincronización adicional. Publicar código y reiniciar
el servicio; recargar el navegador para usar la versión indicada de estáticos.

## Presentación de duración SLA

Bandeja y análisis muestran horas y minutos hasta 24 horas inclusive. Para
duraciones mayores muestran días de 24 horas, horas restantes y minutos cuando
corresponda: 25 horas → 1 día 1 h; 49 h 30 min → 2 días 1 h 30 min.
El formato se genera en el servidor y no necesita JavaScript. Se muestra también
la duración cero, y se omiten valores ausentes, negativos o inválidos.
No cambian las horas corridas, las fechas usadas, el límite de 48 horas ni los
porcentajes de cumplimiento. Publicar bandeja.js con collectstatic y copiarlo al
directorio de estáticos de Nginx para retirar el formateador anterior.
