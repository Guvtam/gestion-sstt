# Avance de estructura profesional

Este documento actualiza el seguimiento; los informes anteriores conservan
la fotografía técnica de cada entrega.

| Área | Estado |
|---|---|
| Reglas compartidas de servicios, cuentas, SLA y preventivos | Implementadas y con regresiones |
| Sincronización por lotes, bloqueo y registro de ejecuciones | Implementados |
| Resolución de coordinadores por lotes durante peticiones | Implementada; proyección local permanente pendiente |
| Casos de uso de edición, revisión, facturación, informes y asignaciones | Separados de HTTP y con pruebas transaccionales |
| Historial de requisiciones | Implementado; requiere migración 0012 |
| Alta automática de cuentas B2C consistente | Unificada entre lectura, sincronización y completar catálogo |
| Anulación financiera auditable y permiso dedicado | Pendiente de definir reglas antes de sustituir el borrado actual |
| Componentes visuales compartidos | Documento común en pantallas operativas y administración; encabezado compartido donde compatible. Filtros, tablas y mensajes pendientes |
| Rendimiento de índices, exportaciones y concurrencia | Pendiente de medir en entorno representativo |
| Usuarios y responsables configurables | Vínculo de login a responsables existentes administrable (migración 0013); catálogo de nuevos responsables pendiente |
| Configuración de despliegue y traslado corporativo | Pendiente de validar en el servidor real |
| Protección de datos y verificación de respaldos | Etapa final aplazada por decisión de la usuaria |

Las pruebas aisladas no certifican la capacidad de la Raspberry ni la recuperación
de sus datos. Los cambios del repositorio no se instalan automáticamente allí.
