# Filtros e indicadores de bandeja separados

La vista orquesta autorización, alcance por coordinador, paginación y
presentación. La selección de entrada y los cálculos no dependen de render.

| Módulo | Contrato |
|---|---|
| dominio/filtros_bandeja.py | Selección inmutable; predeterminados, multiselección y número exacto sin consultas ni request |
| consultas/filtros_bandeja.py | Querysets de contratistas disponibles y tabla; no decide autorización |
| consultas/indicadores_bandeja.py | Indicadores financieros y operativos sobre un queryset ya filtrado y autorizado |
| vistas/bandeja.py | Mensajes HTTP, alcance, selección, paginación y contexto |

Se conservan importables indicador, opciones_contratistas y SIN_TECNICO_FILTRO
desde los módulos anteriores mediante imports de compatibilidad.

## Semántica conservada

- Fecha inicial: día 21 del mes anterior; final: fecha local actual.
- Parámetro ausente no equivale a parámetro explícitamente vacío.
- Cuatro servicios predeterminados solo en la entrada inicial de pagos.
- Bandeja por creación no impone servicio ni estado.
- Contratistas no especificados: disponibles seleccionados.
- Selección explícitamente vacía de contratistas: ningún resultado.
- Sin técnico solo se incluye como opción de la bandeja por creación.
- Servicio editado prevalece; monto editado cero se conserva.
- La fecha inválida de tabla emite el aviso anterior y no filtra por esa fecha.
- Número exacto inválido no amplía la selección.
- Indicadores usan el mismo queryset autorizado que la tabla.

Los módulos de consulta no sustituyen el control de alcance. No deben utilizarse
para otorgar acceso por sí solos.

## Corrección del selector de responsables

La vista y su plantilla todavía validaban y mostraban cuatro responsables
fijos, aunque el catálogo ya era administrable. Ambos consumen ahora el catálogo
activo. Un nuevo responsable aparece y puede filtrarse sin cambiar código.
Se conserva SIN_IDENTIFICAR para usuarios autorizados y la imposición del
responsable de sesión para coordinadores.

## Validación y límites

353 pruebas correctas. Se añaden regresiones de cambio de año, parámetros
vacíos, selección vacía, fechas inválidas, monto cero, servicio corregido,
número exacto, sin técnico y responsable añadido al catálogo.
Cada agregado financiero y operativo mantiene una consulta SQL.

No requiere migraciones, sincronización adicional ni cambios de estáticos.
No se accedió al servidor ni se modificaron datos de las instalaciones.
No se realizó una medición de carga ni una revisión visual en navegador.

Siguen pendientes la extracción de paginación/enriquecimiento de filas y
catálogos auxiliares de bandeja, el resto de la exportación PDF y otros
componentes visuales. No se declara terminada la reorganización.
