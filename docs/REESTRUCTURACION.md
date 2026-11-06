# Reestructuración: reglas compartidas y consultas

## Qué se implementó

La segunda entrega extrae reglas de negocio y consultas reutilizables de las
vistas, manteniendo URLs, permisos, modelos y contratos de respuesta.

| Módulo | Responsabilidad implementada |
|---|---|
| `dominio/cuentas.py` | Código estable de cuenta, clasificación explícita y B2C predeterminado |
| `dominio/servicios.py` | Cuatro servicios principales, alias, clasificación y prioridad del valor editado |
| `dominio/indicadores.py` | Estado de SLA y límite compartido de 48 horas |
| `dominio/pagos.py` | Estados aprobados y opciones de estado de pago vigentes |
| `dominio/fechas.py` | Suma de meses calendario con ajuste de último día |
| `consultas/pagos.py` | Condición de aprobación y monto efectivo SQL |
| `consultas/servicios.py` | Expresión SQL de servicio efectivo, mayúsculas, tildes y espacios exteriores |
| `consultas/preventivos.py` | Consulta preventiva común y último preventivo por código de cuenta |
| `consultas/resumen_facturacion.py` | Categorías, montos, cantidades y distribución por cliente sobre valores facturados |

`cuentas_utils` conserva imports compatibles y la carga del catálogo por lotes.
Los símbolos usados previamente desde `views` y `mantenimientos_preventivos`
permanecen disponibles mediante imports, para no romper consumidores existentes.
El PDF y el calendario ya no importan reglas desde otras vistas.

Los modelos de facturación se registran durante `django.setup()`. No cambian
tablas ni migraciones. Las vistas de escritura y sus transacciones se conservan.

## Correcciones funcionales incluidas

### Último preventivo consistente

Bandeja, análisis y página de preventivos reconocen el servicio corregido
cuando existe y los mismos alias preventivos. Solo una ODT finalizada con fecha
de finalización acredita un mantenimiento realizado.

Se agrupa por código normalizado de cuenta. Por ejemplo, `FIR-100 - Nombre nuevo`
y `fir - 100 - Nombre anterior` corresponden a la misma cuenta. Corregir un
preventivo a otro servicio deja de acreditarlo; corregir otro servicio a
preventivo sí lo acredita. Una cuenta sin código válido no recibe un preventivo
atribuido por coincidencia accidental de texto.

La bandeja carga la fecha después de paginar, sin consultar una vez por cada
ODT. El análisis conserva un máximo de tres consultas de métricas con cuentas
válidas: incidencias agregadas, filas y preventivos agregados. Con selección
vacía o sin códigos reconocibles se omite la consulta preventiva innecesaria.

El agregado preventivo se lee globalmente y se retienen solo los códigos
solicitados; esto permite reconocer nombres históricos sin agregar columnas ni
ejecutar migraciones. No equivale a un índice de cuenta normalizada: para volúmenes
mayores se debe medir e implementar esa proyección mediante una migración aparte.

`con_indicadores_odt` devuelve las anotaciones SQL de SLA/incidencias. La fecha
de último preventivo se agrega con `asignar_ultimos_preventivos` sobre filas ya
obtenidas. Este contrato se usa tanto en la bandeja como en las comparaciones de
pruebas, evitando una subconsulta correlacionada por texto de cuenta.

### Resúmenes financieros consistentes

Historial, resumen de período y detalle de ODT facturadas comparten clasificación
y cálculo, incluyendo alias de renovación/preventivo y categorías con cero ODT.
Las tarjetas de bandeja usan el mismo catálogo de alias en sus agregaciones SQL.
Los filtros de selección conservan sus valores y semántica actuales.

Servicio y monto facturados siguen siendo la instantánea guardada al facturar.
La clasificación B2B/B2C continúa siendo la actual del catálogo; CECO no se infiere.
Los adaptadores de resúmenes mantienen sus formatos previos, incluido el mapa de
montos por cliente de la vista de facturación y el detalle con promedios del
historial. Se conserva el procesamiento por lotes para querysets de items.

La normalización Python de categorías además tolera espacios internos repetidos
en históricos. La expresión SQL normaliza tildes, mayúsculas y espacios exteriores;
no se utiliza para reescribir valores originales o editados.

### Reglas preservadas explícitamente

- Una edición de monto igual a cero prevalece sobre el original.
- Un servicio editado vacío no se interpreta como ausencia de edición.
- Ausencia de revisión y POR_REVISAR siguen siendo aprobados por la regla vigente.
- SLA utiliza 48 horas corridas y distingue pendientes, falta de datos y fechas negativas.
- El calendario conserva su selección y colores; sumar seis meses sigue ajustando
  fin de mes y años bisiestos.
- Se mantienen el alcance de coordinadores y las restricciones de escritura.

## Validación

La suite incluye nuevas regresiones para cuenta renombrada, servicios corregidos
en ambos sentidos, alias, tildes minúsculas, fechas inválidas y límites de SLA,
montos cero, valores facturados y contratos de respuesta. Incluye comparación
de bandeja/análisis/preventivos y presupuesto de consultas independiente de la
cantidad de ODT. Se ejecutan check, detección de migraciones pendientes y suite
completa; verificar el resultado de CI en el PR.

Además se comprobó en un proceso nuevo que los tres modelos de facturación
están registrados después de `django.setup()` sin importar `revisiones.urls`.

## Qué sigue pendiente

- Contener la exposición histórica de datos/configuración del repositorio público.
- Extraer casos de uso transaccionales de edición, revisión y facturación.
- Proyectar coordinadores localmente y quitar consultas SQL por ODT en peticiones.
- Registrar estado/frescura de sincronización y evitar ejecuciones simultáneas.
- Diseñar anulación auditable de períodos con permiso dedicado.
- Separar configuración por entorno y verificar respaldos/restauración en Raspberry.
- Medir índices, concurrencia y memoria con datos autorizados; preparar traslado
  a servidor corporativo y base transaccional.
- Unificar componentes visuales; esta entrega no cambia las pantallas ni sus estáticos.

La normalización de incidencias por cuenta/contratista no se cambia en esta
entrega: no debe confundirse con el cálculo del último preventivo ni con el
contador global de incidencias por código de cuenta del dashboard.

## Despliegue

Sin nuevas migraciones ni cambios de estáticos. Conservar configuración y base
del piloto. La primera parte del PR completa dependencias: instalarlas en el
entorno virtual si aún no se habían instalado manualmente. Validar un release
antes del pull/reinicio; consultar [operación](OPERACION.md).
