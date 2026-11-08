# Consultas auxiliares y mensajes compartidos

consultas/catalogos_bandeja.py concentra la unión ordenada de servicios
originales/editados, los estados y los filtros previos de opciones AJAX.
Se conserva el catálogo global existente, la carga diferida de estados
y la restricción por coordinador aplicada posteriormente en la vista.

No se alteran fechas, predeterminados, servicios efectivos, selección vacía
ni permisos. Las consultas de opciones no conceden alcance por sí mismas.

componentes/mensajes.html es utilizado por bandeja, facturación por período,
historial y administración de cuentas. Se conservan sus contenedores y estilos
de sección. Los errores se anuncian con role=alert; el resto con role=status.
Las etiquetas adicionales no impiden reconocer el nivel error. Se mantiene
autoescape; no se interpolan clases arbitrarias desde las etiquetas.

La revisión estática de imports en dominio, consultas, casos_uso y pdf no
encontró dependencias hacia las vistas de la aplicación en esas capas.
Esto no es una auditoría completa ni sustituye las pruebas del despliegue.

376 pruebas correctas, check sin incidencias y sin migraciones pendientes.
Nuevas regresiones verifican opciones, carga diferida, servicio corregido,
alcance del queryset recibido, almacenamiento de mensajes, roles y escape HTML.
No se realizó inspección visual en navegador ni prueba remota.

No requiere migraciones ni cambios de estáticos.
Los componentes de tablas y filtros con contratos diferentes siguen sin
unificarse de forma general. Ver PRUEBA_SERVIDOR.md para la aceptación real.
