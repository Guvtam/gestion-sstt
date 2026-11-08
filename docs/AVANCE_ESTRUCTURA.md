# Avance de estructura profesional

Este documento actualiza el seguimiento; los informes anteriores conservan
la fotografía técnica de cada entrega.

| Área | Estado |
|---|---|
| Reglas compartidas de servicios, cuentas, SLA y preventivos | Implementadas y con regresiones |
| Sincronización por lotes, bloqueo y registro de ejecuciones | Implementados |
| Resolución de coordinadores por lotes durante peticiones | Implementada con proyección local renovable (0015); requiere carga y programación en despliegue |
| Casos de uso de edición, revisión, facturación, informes y asignaciones | Separados de HTTP y con pruebas transaccionales; actualización de cuentas incorporada |
| Historial de requisiciones | Implementado; requiere migración 0012 |
| Alta automática de cuentas B2C consistente | Unificada entre lectura, sincronización y completar catálogo |
| Anulación financiera auditable y permiso dedicado | Pendiente de definir reglas antes de sustituir el borrado actual |
| Componentes visuales compartidos | Base, opciones de servicios, errores, mensajes y navegación compartidos; columnas y formularios específicos conservan su contrato |
| Rendimiento de índices, exportaciones y concurrencia | Pendiente de medir en entorno representativo |
| Usuarios y responsables configurables | Vínculos de login (0013) y catálogo de nuevos responsables (0014) administrables |
| División de módulos | Vistas, bandeja, catálogos auxiliares y exportación separados; otros componentes y revisión del despliegue pendientes |
| Configuración de despliegue y traslado corporativo | Pendiente de validar en el servidor real |
| Protección de datos y verificación de respaldos | Etapa final aplazada por decisión de la usuaria |

Las pruebas aisladas no certifican la capacidad de la Raspberry ni la recuperación
de sus datos. Los cambios del repositorio no se instalan automáticamente allí.

Ver [detalle de la evolución operativa](EVOLUCION_OPERATIVA.md) para los límites de vigencia y la conciliación del calendario.

La [bandeja modular](BANDEJA_MODULAR.md) separa selección y agregaciones y actualiza el selector de coordinadores al catálogo administrable.

La [preparación de filas](FILAS_BANDEJA.md) distingue lecturas por lote y atributos de presentación sin consultas adicionales.

La [exportación modular](EXPORTACION_MODULAR.md) separa HTTP, lecturas, composición y construcción del documento.

[Catálogos y mensajes](CATALOGOS_MENSAJES.md) completan las consultas auxiliares de bandeja. La [guía de prueba del servidor](PRUEBA_SERVIDOR.md) permite comprobar la instalación real.

La [navegación compartida](NAVEGACION_COMPARTIDA.md) conserva multiselección y paginaciones independientes.

[Revisión estructural de la etapa](CIERRE_REVISION_ESTRUCTURAL.md): guardas automatizadas, actualización transaccional de cuentas y límites pendientes de entorno.
