# Filtro de Pago técnico

La bandeja y ODT por creación incluyen una lista de importes con casillas, búsqueda,
selección de todos y desmarcado de todos. Se aplica con **Aplicar filtros**.

La lista usa el pago efectivo: monto editado cuando existe (incluso $0 o $2),
y monto SoftGuard en otro caso. Conserva centavos y distingue importes exactos.
Muestra los valores de todas las páginas del resultado autorizado, tras aplicar
los demás filtros; no limita las opciones a las 50 filas visibles. Una selección
que dejó de existir se conserva en la lista para poder desmarcarla.

Sin selección explícita se incluyen todos los importes. Desmarcar todas las
casillas y aplicar devuelve cero resultados. Seleccionar todos quita la restricción
de monto al enviar el formulario. Buscar en la lista no cambia las casillas.

El filtro se conserva en los enlaces de paginación y guardados. Los indicadores,
el PDF de aprobados y la previsualización/confirmación de facturación respetan
la selección de montos; conservan sus reglas adicionales de aprobación y permisos.
La firma de confirmación incluye el filtro, por lo que cambiarlo exige una nueva
previsualización. No se alteran instantáneas, bloqueos ni reglas de pago.

No cambia el orden de las ODT: pendientes, procesadas y resto; dentro de cada
prioridad, cuenta, código técnico, fecha de finalización ascendente y número
 descendente. ODT por creación conserva su orden sin prioridad de correcciones.
El retorno de un guardado mantiene temporalmente la página y las filas visibles.

No requiere migraciones ni cambios de usuarios, permisos o datos. Tras integrar,
publicar estáticos, copiarlos al directorio de Nginx y reiniciar el servicio.
