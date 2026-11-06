# Revisión técnica del sistema SSTT

Fecha: 6 de noviembre de 2026.
Base revisada: `349b1294101370286078f6ba2552f298e2e225fd` (main, después del PR 33).

## Alcance y límites

Revisión del árbol del repositorio, configuración, modelos y migraciones,
rutas, vistas, acceso de coordinadores, contratistas, facturación, PDF,
clasificación de cuentas, indicadores, preventivos, calendario y sincronización.
Se ejecutan comprobaciones Django, detección de migraciones pendientes y pruebas
automatizadas con base aislada. No se descargaron ni abrieron las bases SQLite
publicadas, ni se leyó el contenido del `.env`.

No se ha accedido a la Raspberry, SQL Server ni Nginx. No se certifica la
configuración efectiva del piloto, capacidad con siete usuarios concurrentes,
recuperación de respaldos, permisos del usuario SQL ni TLS del servidor.
La revisión de código y las pruebas no reemplazan una prueba de aceptación
con los usuarios ni una auditoría de seguridad externa.

## Diagnóstico

Conviene mantener un monolito Django modular. Ya hay separación útil en
contratistas, facturación, correcciones, cuentas y análisis. Los riesgos
principales son exposición de datos en el repositorio, despliegue poco
reproducible, dependencia del origen SQL durante peticiones y divergencias
entre reglas repetidas. Una reescritura completa aumentaría el riesgo del piloto.

## Hallazgos priorizados

| ID | Prioridad | Evidencia en código o repositorio | Consecuencia y acción |
|---|---|---|---|
| R01 | Crítica | Repositorio público; `config/.env`, `db.sqlite3`, dos respaldos SQLite, `tecnicos.xlsx` y catálogo CSV versionados. | Posible exposición de datos y credenciales. Restringir visibilidad; revisar y rotar cualquier secreto real publicado. Respaldar fuera del repositorio, retirar archivos del seguimiento y limpiar historial con un procedimiento coordinado. No basta `.gitignore` ni borrar la última versión. No se inspeccionó el contenido de esos archivos. |
| R02 | Alta | `config/settings.py`: DEBUG activado por defecto, clave de desarrollo de reserva, hosts fijos, validadores de contraseña vacíos y `load_dotenv(..., override=True)`. | Un despliegue sin configuración puede arrancar inseguro o sobreescribir variables del servicio. Separar base/desarrollo/piloto/producción, exigir secretos en entornos servidos y validar hosts y cookies según HTTPS real. La Raspberry usa otro módulo local cuya configuración no se ha verificado. |
| R03 | Alta | `contratistas_disponibles_ajax` solo tenía `login_required`. | Un usuario autenticado sin permiso de bandeja podía obtener nombres de contratistas. Se agrega el mismo permiso de la bandeja y pruebas de acceso anónimo, denegado y autorizado. |
| R04 | Alta | `acceso_coordinadores.limitar_odts_coordinador` itera ODT; `identificar_coordinador_odt` consulta asignación local y, sin ella, historial SQL por ODT. `views.bandeja` repite identificación para filtro y filas. | La latencia y disponibilidad del origen afectan páginas y control de alcance. Construir proyección local de responsables durante sincronización, con fecha de verificación, prioridad de asignación manual y política explícita ante origen caído. Mantener denegación segura y pruebas de aislamiento. |
| R05 | Alta | `sincronizar_odts`: `fetchall`, conjunto completo de números y `update_or_create` en una transacción por fila. No hay registro persistente de ejecución ni marca de lote completo. | Importación costosa en 1 GB RAM; una interrupción deja un lote parcialmente actualizado y poca trazabilidad. Añadir ejecución de sincronización, lotes acotados, bloqueo de ejecución y reintentos controlados; conservar las ediciones locales. No confundir frecuencia del timer con frescura del DW. |
| R06 | Alta | SQLite en configuración principal; edición y facturación usan `select_for_update`. | Los bloqueos por fila no están disponibles en SQLite. Las restricciones únicas protegen duplicados, pero no equivalen a concurrencia completa y pueden aparecer bloqueos de base. Ensayar edición/facturación simultánea; planificar PostgreSQL para el servidor corporativo, sin imponerlo ahora al piloto. |
| R07 | Alta | `historial_facturacion.eliminar_periodo_facturacion` permite staff, elimina items/facturaciones/período y usa el motivo solo en la petición. | El borrado libera ODT y pierde evidencia de la operación; staff no equivale a permiso financiero específico. Diseñar anulación auditable y permiso dedicado. Requiere decisión de negocio antes de modificar períodos ya utilizados. |
| R08 | Media | `requirements.txt` solo declaraba Django y openpyxl; imports usan dotenv, pyodbc, reportlab e imágenes. Sin workflow de pruebas en el árbol revisado. | Instalaciones nuevas incompletas y regresiones no detectadas. Se completan dependencias, configuración de pruebas independiente y workflow de comprobaciones/tests. Falta aprobar versiones exactas y política de actualizaciones. |
| R09 | Media | `views.py` supera 2.100 líneas, `exportar_pdf.py` 1.100; varias vistas comparten reglas mediante imports desde otras vistas. | Responsabilidades acopladas y cambios difíciles de validar. Extraer primero reglas puras y consultas, luego casos de uso transaccionales; preservar rutas y contratos existentes. |
| R10 | Media | `indicadores_odt` y `metricas_analisis` buscan último preventivo por servicio original y texto completo de cuenta; `mantenimientos_preventivos` usa servicio efectivo, alias y código normalizado. | Una corrección de servicio o cambio de nombre/dirección puede producir indicadores distintos por pantalla. Unificar identidad de cuenta, servicio efectivo y definición de preventivo; agregar regresiones con esas variaciones. No asumir que coinciden porque coincidan los ejemplos actuales. |
| R11 | Media | `facturacion.resumen_costos_periodo` e `historial_facturacion.resumen_costos_periodo` duplican clasificación; servicios principales y alias también se repiten. | Tarjetas, PDF y análisis pueden divergir. Crear un módulo común de servicios y resúmenes con pruebas de equivalencia antes de sustituir implementaciones. |
| R12 | Media | Fechas de creación/finalización/visita de ODT no tienen índices declarados; bandeja filtra con `__date`; preventivos recorre catálogo y ODT antes de paginar. | El coste crece con los datos. Medir consultas/tiempos con una copia autorizada; añadir índices y normalización mediante migraciones evaluadas, no a ciegas. Analítica ya tiene consultas por lotes, pero materializa resultados para calcular gráficos. |
| R13 | Media | Historial SQL e imágenes remotas se consultan durante exportación PDF, con límites y allowlist de imágenes ya presentes. | Exportaciones largas ocupan workers de la Raspberry y dependen de servicios externos. Medir tamaños/tiempos, acotar selección y valorar generación en segundo plano si se supera el presupuesto. No desactivar las validaciones de imagen. |
| R14 | Media | Roles especiales por nombre (`admin`, `jiturriaga`), mapa de cuatro coordinadores en código y permisos personalizados creados por comando. | Altas/cambios de personal requieren código y pasos manuales. Diseñar vínculo usuario-responsable y permisos explícitos preservando las excepciones aprobadas; no ampliar permisos automáticamente al refactorizar. |
| R15 | Media | `completar_catalogo_cuentas` crea cuentas SIN_CLASIFICAR aunque sincronización crea B2C; lectura común aplica B2C por defecto. | Existen valores persistidos y valores efectivos distintos. Documentar la proyección, unificar comandos y comprobar filtros SQL tras cambios de catálogo. No inferir CECO a partir de B2C. |
| R16 | Media | Motivos financieros se guardan en eventos, pero no hay evidencia en el repositorio de verificación de restauración, retención de backups, monitorización o release reproducible. | La recuperación operativa sigue sin demostrar. Ensayar backup/restauración y traslado con conciliación de cantidades y montos; revisar el servidor real antes de afirmar disponibilidad de producción. |

## Bases útiles que se conservan

- Vistas con login y permisos, operaciones de escritura mediante POST y CSRF.
- Coordinadores limitados a sus ODT; la asignación local prevalece sobre SQL.
- Transacciones, restricciones únicas de período/contratista y ODT facturada única.
- Servicio y monto facturados guardados como instantánea, separados del origen.
- Eventos de revisión/corrección con usuario y fecha.
- Regla B2B/B2C compartida por lecturas, PDF y sincronización.
- PDF con allowlist HTTPS, sin redirecciones y con límites de descarga de imagen.
- Cobertura automatizada de reglas de acceso y funciones incorporadas al piloto.

Estas bases no significan que toda operación tenga auditoría completa ni que
SQLite garantice el bloqueo que tendría una base con bloqueos por fila.

## Etapas y criterios de aceptación

1. **Contención y reproducibilidad.** Revisar exposición de R01, proteger
   secretos/datos, adoptar pruebas aisladas y establecer un release verificable.
   Criterio: instalación limpia, pruebas y comprobaciones aprobadas; respaldo
   restaurado en entorno separado. La limpieza histórica exige coordinar PC y Pi.
2. **Consistencia del dominio.** Centralizar servicios, cuentas, SLA y resúmenes;
   probar igual entrada/igual salida en bandeja, preventivos, análisis y PDF.
   Criterio: regresiones para servicio corregido, cuenta renombrada, límites de
   fecha, cero, nulos y períodos vacíos. No cambiar reglas de negocio silenciosamente.
3. **Integración desacoplada.** Sincronización por lotes con estado y responsable
   local; peticiones habituales sin consultas SQL por cada ODT. Criterio: fallar
   el origen no expone ODT ajenas y no borra cambios locales; ejecución repetible.
4. **Operación corporativa.** Base transaccional, HTTPS, permisos de servicio,
   logs y alertas, procedimiento de anulación, restauración y rollback.
   Criterio: aceptación concurrente con siete usuarios y conciliación de datos
   del piloto antes de cortar al servidor nuevo.

## Cambios incluidos en esta primera revisión

- Documentación de arquitectura actual/objetivo y riesgos con evidencia.
- Dependencias de aplicación, desarrollo y servidor separadas.
- `config.settings_test`: base en memoria, sin carga de `.env` ni datos del piloto.
- Comprobaciones y suite automatizada mediante GitHub Actions.
- Permiso de bandeja en endpoint AJAX y pruebas de regresión.
- `.gitignore` preventivo. No se eliminan archivos existentes ni se purga historial.

No se modifican la configuración activa de la Raspberry, modelos ni migraciones.
Los hallazgos restantes son trabajo pendiente, no correcciones ya aplicadas.

## Resultado de validación de esta entrega

Este informe conserva la fotografía de la revisión inicial. La extracción de
reglas, corrección de último preventivo y unificación de resúmenes posteriores
se detallan en [reestructuración](REESTRUCTURACION.md), que actualiza el estado
de R09, R10 y R11. La contención de R01 continúa pendiente.

- `check --settings=config.settings_test`: sin incidencias.
- `makemigrations --check --dry-run --settings=config.settings_test`: sin cambios.
- Suite `contratistas revisiones`: 138 pruebas aprobadas en SQLite en memoria.
- Ejecución local con Python 3.12 y Django 5.2.19; workflow configurado para
  Python 3.13, versión utilizada en la Raspberry. Su ejecución en GitHub se
  debe comprobar tras publicar el PR; no se afirma que ya haya pasado.
- No se realizó una prueba de carga, restauración de datos reales ni validación
  visual en navegador en esta revisión.
