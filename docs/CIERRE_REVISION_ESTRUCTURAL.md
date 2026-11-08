# Revisión de la etapa de organización interna

## Comprobado en el repositorio

- Vistas operativas separadas por responsabilidad y rutas compatibles.
- Reglas de cuentas, servicios, fechas, pagos y SLA compartidas.
- Selección, filtros, indicadores, paginación y filas de bandeja separados.
- Exportación separada en HTTP, consultas, composición, documento e imágenes.
- Catálogos auxiliares y componentes de mensajes/navegación compartidos.
- Actualización del catálogo trasladada a un caso de uso transaccional.
- Fachadas de compatibilidad sin funciones, clases ni ejecución de negocio.

La suite de 397 pruebas pasa con la configuración aislada.
Django check no informa incidencias y no hay cambios de migración pendientes.

## Guardas automatizadas

test_limites_arquitectura revisa AST de los módulos extraídos:
- Dominio y presentación no importan Django, modelos ni vistas.
- Consultas, casos_uso, PDF, dominio y presentación no importan vistas de aplicación.
- Las fachadas views y exportar_pdf conservan solo docstring e imports.

Son guardas estáticas de los directorios revisados. No detectan todas las
dependencias dinámicas, no sustituyen la revisión de reglas y no certifican
seguridad ni rendimiento del despliegue.

## Límites y trabajo restante

La reorganización principal no implica que todos los adaptadores sean mínimos.
El cambio de estado de modificación se trasladó posteriormente a un caso de
uso con autorización y auditoría transaccional (GESTION_CORRECCIONES.md).
La eliminación de facturación conserva su operación anterior:
la anulación auditable exige definir reglas de negocio.

Otros módulos de lectura de análisis/preventivos conservan consultas propias.
No se propone trasladarlos solo por uniformidad de nombres; extraer cuando haya
duplicación, cambios de responsabilidad o un contrato compartido comprobable.

Pendientes de entorno:
- Prueba funcional y visual con los roles reales.
- Conciliación entre bases locales y origen.
- Medición de exportaciones grandes, memoria y concurrencia.
- Configuración efectiva y traslado corporativo.
- Protección de datos y verificación de respaldos en la etapa acordada.

Esta entrega no cambia configuración, servicios, base ni programación remota.
La guía PRUEBA_SERVIDOR.md define la comprobación del entorno real.
No requiere nuevas migraciones ni sincronización adicional.

Actualización de esta revisión: la suite posterior de gestión de correcciones tiene 410 pruebas aprobadas.
