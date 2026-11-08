# Navegación compartida de listados

componentes/paginacion.html es utilizado por bandeja, cuentas, análisis,
preventivos, ODT modificadas e historial de requisiciones.
Preventivos incluye dos controles independientes: cuentas y detalle de una cuenta.

El componente conserva la variante agrupada de botones y la variante en línea,
sus clases de sección, contador, enlaces disponibles y comportamiento de página
única. Cuentas mantiene el contador aunque no haya páginas adicionales.

navegacion_sstt.enlace_pagina construye URLs mediante QueryDict:
- Conserva filtros multivalor y valores explícitamente vacíos.
- Sustituye la página actual sin acumular parámetros page duplicados.
- Cambiar page_detalle conserva page y el resto de filtros.
- Conserva el ancla del historial preventivo.
- Los números de página no se formatean con separadores de miles.
- Solo admite page y page_detalle; no produce enlaces con página no positiva.

El HTML mantiene autoescape. La navegación tiene etiqueta accesible.
No consulta base de datos ni concede acceso: las vistas siguen filtrando y
autorizando cada petición.

Las columnas y formularios de las tablas conservan sus contratos específicos.
Compartir navegación no implica imponer una tabla genérica a todos los dominios.

## Validación y límites

385 pruebas correctas, check sin incidencias y sin migraciones pendientes.
Nuevas regresiones cubren primera/intermedia/última página, página única,
multiselección, selección vacía, paginaciones independientes, ancla, caracteres
Unicode, texto hostil y números grandes.

No cambia columnas, permisos, modelos o archivos estáticos.
No requiere migraciones ni sincronización adicional.
No se realizó una comprobación visual en navegador ni prueba del servidor.
La guía PRUEBA_SERVIDOR.md incluye la comprobación funcional de navegación.
