# Arquitectura SSTT

## Situación actual

Un proceso Django sirve páginas, valida permisos, ejecuta reglas de revisión y
facturación y genera PDF. Los datos de ODT se sincronizan desde SQL Server a la
base local; la identificación de coordinador y los historiales todavía consultan
SQL durante ciertas peticiones. Nginx y Gunicorn existen en el piloto según la
instalación realizada, pero sus archivos no forman parte del repositorio revisado.

Los modelos de facturación están en `facturacion_models.py` y se importan desde
vistas. En una extracción posterior conviene registrar todos los modelos desde
el módulo de modelos, sin depender de la carga de rutas para descubrirlos.
Preservar nombres de tablas, app labels y migraciones al reorganizar.

## Objetivo: monolito modular

Mantener Django, las aplicaciones `revisiones` y `contratistas`, las URLs y las
tablas existentes. Organizar responsabilidades dentro de ellas antes de crear
más aplicaciones o servicios independientes.

| Capa | Responsabilidad | No debe hacer |
|---|---|---|
| Vistas y formularios | Validar entrada HTTP, permisos y devolver respuesta | Duplicar reglas financieras ni consultar SQL por fila |
| Casos de uso | Editar ODT, revisar pago, facturar, gestionar corrección; transacción y eventos | Depender de templates o parámetros HTTP sin validar |
| Consultas | Filtrar, agregar, paginar y aplicar alcance del usuario | Modificar datos al mostrar una página |
| Dominio | Identidad de cuenta, servicio efectivo, clasificación, SLA, períodos y transiciones | Abrir conexiones o importar vistas |
| Integración | Leer DW, transformar y sincronizar; registrar ejecución y frescura | Sobrescribir revisiones o valores manuales |
| Presentación | Templates, componentes, CSS y JS comunes | Decidir permisos o cálculos financieros autoritativos |
| Operación | Configuración por entorno, logs, pruebas, backup, release | Guardar datos o credenciales en Git |

Directorios objetivo (aún no implementados por completo):

- `config/`: configuración común y módulos explícitos por entorno.
- `revisiones/dominio/`: reglas puras de cuentas, servicios, SLA y estados.
- `revisiones/consultas/`: bandeja, calendario, análisis y facturación.
- `revisiones/casos_uso/`: operaciones transaccionales con auditoría.
- `revisiones/integraciones/`: acceso al DW y transformación de registros.
- `revisiones/presentacion/`: vistas y exportación usando las capas anteriores.
- `contratistas/`: catálogo, validación, equivalencias e importación propios.
- `templates/` y `static/`: base visual y componentes reutilizables.
- `docs/`: reglas, operación, decisiones y evidencia de validación.

No crear todos estos directorios vacíos. Extraer una responsabilidad real por PR
y conservar temporalmente imports compatibles donde los tests o rutas lo necesiten.

## Fuentes de verdad

| Información | Fuente autoritativa | Tratamiento |
|---|---|---|
| Estado y fechas operativas originales, servicio y monto de origen | DW de SoftGuard | Sincronización de lectura; registrar fecha de carga y ejecución local |
| Servicio/monto corregidos, estado pago e informe | Base SSTT | Escritura autorizada, validación, transacción y evento |
| Asignación manual de coordinador | Base SSTT | Prevalece; solo perfiles autorizados |
| Coordinador inferido | Acciones autorizadas del historial SoftGuard | Proyección local propuesta, con fecha de verificación |
| CECO y clasificación explícita | Catálogo SSTT | Validar y auditar; sin CECO conocido mostrar revisión pendiente |
| B2C predeterminado | Regla de dominio | Código válido sin clasificación explícita; código inválido queda sin clasificar |
| Contratista y datos bancarios | Catálogo SSTT + equivalencias validadas | Permisos específicos para datos bancarios |
| Servicio y monto facturados | `FacturacionODT` | Instantánea de facturación; no recalcular desde valores actuales |
| Tipo cliente/CECO mostrados en historia | Catálogo actual según regla vigente | No confundir con instantánea histórica; si se exige inmutabilidad fiscal, diseñar campos snapshot por separado |

## Contratos de negocio que necesitan pruebas compartidas

1. Servicio efectivo: un valor editado no nulo prevalece sobre el de origen.
   Definir explícitamente qué significa una cadena vacía antes de normalizarla.
2. Cuenta: usar código normalizado; un cambio en nombre/dirección no crea otra
   identidad. Separar cuenta desconocida de código inválido.
3. Último preventivo: misma identidad de cuenta, servicio efectivo reconocido,
   estado Finalizado y fecha de finalización válida. Próximo estimado: seis meses
   calendario; no confundir estimación con visita realmente programada.
4. Incidencias: documentar si se cuentan cuentas o ODT y si la agrupación incluye
   contratista. Actualmente conviven ambos indicadores; no son intercambiables.
5. SLA: 48 horas corridas entre creación y finalización; excluir fechas inválidas
   del denominador y mostrar el número evaluable. No equivale a SLA contractual
   por cliente sin una regla adicional aprobada.
6. Pago: POR_REVISAR y ausencia de revisión se tratan como aprobado en la lógica
   vigente. Es una decisión explícita que debe conservarse hasta que negocio
   autorice cambiarla, aunque el nombre histórico sugiera otra cosa.
7. Corrección: Pendiente → Procesada manualmente; Actualizada por coincidencia
   comprobada con origen. Una nueva diferencia vuelve a Pendiente.
8. Facturación: ODT única, finalizada, aprobada, dentro de período y selección;
   validación repetida en servidor dentro de la transacción.

## Orden de extracción

1. Pruebas y documentación, sin cambios de modelo (esta entrega).
2. Módulo común de servicios y cuentas; pruebas de equivalencia entre pantallas.
3. Consultas compartidas con fechas e identidad uniformes; medir e indexar.
4. Casos de uso de pago/facturación/correcciones con alcance del usuario explícito.
5. Sincronización y responsables locales; sacar consultas SQL del camino habitual.
6. Templates base, navegación, multiselect y estilos comunes.
7. Configuración corporativa y migración de base, con ensayo de restauración.

Cada PR debe incluir comportamiento preservado/cambiado, pruebas relevantes,
impacto sobre datos y procedimiento de despliegue. Evitar cambios simultáneos
de organización, nombres de tablas y reglas de negocio.
