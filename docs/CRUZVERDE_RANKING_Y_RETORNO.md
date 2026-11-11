# Servicio Cruzverde, ranking y retorno al guardar

Se agrega MANTENIMIENTO NUEVA INSTALACION CRUZVERDE al catálogo principal (siete servicios), al selector de edición, a los filtros por defecto y a las tarjetas de pagos y facturación. El resumen de facturación y el PDF reconocen su categoría, conservando los valores de cada instantánea. No se agrupa con otros servicios de instalación ni se clasifica como preventivo. La sincronización ya importa todos los servicios: no se cambia su alcance.

Con filtros antiguos explícitos, pulsar Limpiar para incluir el nuevo servicio. Las ODT deben existir en la base local tras la sincronización habitual.

El ranking de análisis de ODT muestra hasta veinte cuentas. Mantiene un área visible de aproximadamente diez filas (máximo 600 px) y agrega desplazamiento vertical interno, accesible por teclado. Se mantienen las reglas de período, filtros y desempate.

Al guardar una edición, el navegador envía los números de las filas visibles (máximo cincuenta) y la página actual. El servidor conserva ese orden para la respuesta de retorno, vuelve a aplicar el alcance autorizado y los filtros vigentes, y recalcula todos los indicadores. Si una ODT deja de cumplir los filtros, no se vuelve a incluir. El navegador restaura las posiciones vertical y horizontal y elimina los parámetros de retorno. La paginación y otras navegaciones vuelven a utilizar la prioridad habitual de correcciones; no se congela globalmente el orden de la bandeja.

No hay migraciones ni cambios de permisos. No se reemplaza la base de datos ni se reescriben correcciones o facturas históricas. Al desplegar, publicar estáticos, copiarlos al directorio servido por Nginx y reiniciar Gunicorn. Actualizar navegador con Ctrl+F5.
