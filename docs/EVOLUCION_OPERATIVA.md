# Calendario, responsables locales y componentes

## Diferencia entre calendarios

Las capturas muestran 9 y 76 visitas, pero no permiten comprobar si ambas
instalaciones tienen la misma base, origen y filtros. No se accedió al servidor.

Se corrigió un caso concreto de omisión: FechaPago SQL de tipo DATE llegaba
como datetime.date y la transformación exigía datetime. Se descartaba toda la
ODT, incluidas sus fechas de visita y finalización. FechaPago admite ahora DATE
y lo representa a medianoche local; creación y finalización mantienen la
validación estricta con hora. Fechas nulas y fechas centinela conservan su regla.

El calendario muestra visitas locales disponibles, visitas visibles con filtros
y último intento de sincronización. No infiere visitas por fecha de finalización.

Diagnóstico sin escritura (usar la configuración activa del entorno):

    python manage.py diagnosticar_calendario --mes 2026-11 --comparar-origen --settings=CONFIGURACION_ACTIVA

Sin --comparar-origen solo consulta la base local. La comparación muestra
cantidades agregadas locales y del origen; no importa registros ni lista
cuentas. Debe ejecutarse en las instalaciones que se quieran conciliar.
Las consultas no constituyen una instantánea transaccional común entre las
dos bases; evitar comparar durante actualizaciones del DW.

Tras instalar la corrección, una sincronización normal reimporta las filas
válidas del origen. No recupera registros ausentes del propio DW ni reemplaza
la comprobación del resultado real del servidor.

## Catálogo de responsables

La migración 0014 crea ResponsableSoftGuard e incorpora las cuatro identidades
históricas. Administración permite agregar nombre, identificador numérico real
del origen, identidad de usuario y estado activo. No se inventan IDs del origen.

Los identificadores son de solo lectura después de crearlos; nombre y estado
siguen siendo editables. Para una identidad distinta, crear un responsable
nuevo y desactivar el anterior, conservando los vínculos históricos.

El catálogo administrable se utiliza para inferencia, vínculos de login,
asignación manual, selectores de bandeja y ODT modificadas.
Las identidades históricas conservan compatibilidad; un registro explícito
prevalece y su desactivación se respeta. No se permite borrar desde admin.

Un usuario reconocido como coordinador no se convierte en usuario sin
restricciones al desactivar su identidad. Un vínculo inactivo sigue denegado.
Las excepciones administrativas actuales se conservan.

## Proyección local de responsables ODT

La migración 0015 crea la proyección con resultado, fecha de verificación y
firma del catálogo. Renovación independiente:

    python manage.py sincronizar_coordinadores --settings=CONFIGURACION_ACTIVA

O después de importar ODT, en una sola invocación:

    python manage.py sincronizar_odts --con-coordinadores --settings=CONFIGURACION_ACTIVA

La opción --con-coordinadores debe añadirse a la programación de sincronización
del despliegue para renovar periódicamente. Esta entrega no modifica timers
ni servicios remotos. En simulación de ODT no se renuevan responsables.

La renovación lee lotes de hasta 250 y escribe cada lote en transacción con
upsert masivo. Comparte el bloqueo de sincronización. Un fallo conserva lotes
confirmados y la versión anterior del lote fallido; el comando indica error.
El historial de sincronización de ODT describe esa importación, no certifica
que la renovación posterior de responsables se haya completado.

Prioridad de lectura:
1. Asignación manual SSTT.
2. Proyección con firma vigente y verificación no anterior a seis horas.
3. Consulta al origen por lotes.

SSTT_COORDINADORES_VIGENCIA_HORAS permite ajustar la ventana; cero desactiva
su uso. La proyección representa el responsable en su última verificación,
no garantiza reflejar cambios instantáneos de SoftGuard. Un cambio del catálogo
invalida la firma. No se autoriza con una proyección caducada si falla el origen.

El acceso operativo por lotes usa dos consultas locales por lote, independientes
de su cantidad de ODT. La función de compatibilidad individual que consulta
directamente el historial del origen sigue disponible para consumidores antiguos
y para verificaciones explícitas del origen.

## Estructura y presentación

- Opciones multiselección de servicios compartidas entre calendario y análisis.
- Errores de filtros compartidos entre calendario, análisis y preventivos.
- Consulta mensual del calendario separada en consultas/calendario.py y
  reutilizada por el diagnóstico.
- Colores, estilos y primitivas PDF separados en pdf/componentes.py.
- Los nombres exportados por exportar_pdf se conservan para compatibilidad.
- Filtros, tablas, mensajes y módulos grandes siguen requiriendo extracción
  gradual; no se declara terminada la reorganización completa.

## Validación y aplicación

Aplicar migrate con la configuración activa antes de iniciar esta versión.
La proyección queda vacía hasta ejecutar su renovación.

La suite incluye una carga sintética de 76 visitas con 47 realizadas,
19 abiertas y 10 atrasadas; confirma que DATE en FechaPago no omite esas ODT.
También prueba permisos, desactivación, nuevo responsable, caducidad, firma,
prioridad manual, idempotencia, lotes y diagnóstico de solo lectura.

Los resultados de prueba no demuestran que el servidor ya tenga esas 76 visitas.
No se instaló esta entrega en el despliegue ni se verificaron respaldos.
