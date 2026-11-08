# Vistas HTTP separadas por responsabilidad

views.py conserva imports de compatibilidad y deja de implementar peticiones.
Las rutas importan directamente los módulos de vistas, sin pasar por esa fachada.

| Módulo | Responsabilidad |
|---|---|
| vistas/bandeja.py | Bandeja por finalización/creación, indicadores y opciones de contratistas |
| vistas/odt.py | Detalle e historial de una ODT |
| vistas/operaciones_odt.py | Adaptadores de edición, revisión, informe, corrección y asignación |
| vistas/cuentas.py | Consulta y actualización del catálogo de cuentas |
| vistas/correcciones.py | Listado de ODT modificadas |
| vistas/respuestas.py | Traducción compartida de errores de operación a HTTP |

Se conservan nombres de URL, paths, argumentos, decoradores y contratos de
respuesta. También se mantienen las transacciones, mensajes, consultas y reglas
existentes. Los casos de uso continúan en casos_uso; no se duplican.

Las funciones y constantes de negocio usadas desde views siguen importables.
Los consumidores nuevos deben importar desde el módulo que les corresponde.
Las pruebas que simulaban dependencias de views ahora las simulan en el módulo
donde se utilizan; sus expectativas y comprobaciones funcionales se conservan.

## Validación y límites

Se comparó la estructura AST de las 17 funciones trasladadas, incluidos sus
decoradores, contra la versión anterior: solo cambian niveles de imports
relativos. La suite completa y controles Django verifican los flujos existentes.

Esta extracción no modifica modelos, migraciones, plantillas ni estáticos.
No requiere migraciones ni vuelve a sincronizar datos.
No se accedió a bases del despliegue ni se validó el servidor.

La función principal de bandeja sigue siendo grande. Extraer su construcción
de filtros, consultas y contexto es una etapa posterior con sus propios
contratos y pruebas. También siguen pendientes partes de exportación PDF.
Separar archivos no implica que toda la arquitectura haya quedado terminada.

Etapa posterior aplicada: [filtros e indicadores de bandeja](BANDEJA_MODULAR.md). La paginación y el enriquecimiento siguen en la vista.
