# Prueba del entorno servido después de la reorganización

La prueba valida el despliegue real. La suite aislada no certifica memoria,
latencia SQL, permisos efectivos del servicio o uso simultáneo del servidor.
Esta guía no ejecuta acciones remotas ni modifica la programación de tareas.

## Preparación

- Fusionar los PR que se instalarán y anotar el commit validado.
- Trabajar en la copia del entorno de pruebas y su entorno virtual.
- Comprobar git status antes de actualizar. Conservar cambios locales de
  configuración y datos; resolver conflictos antes de continuar.
- No sustituir una base por la del otro equipo ni usar reset/clean para
  descartar cambios de datos.
- Usar siempre el mismo módulo de settings y la misma base que el servicio.
  CONFIGURACION_ACTIVA es un marcador que debe sustituirse.

Durante actualización y migraciones, detener el servicio según el procedimiento
actual; volver a iniciarlo después de completar las comprobaciones.
No se incluyen nombres de servicios, rutas o credenciales del despliegue.

    git status --short
    git branch --show-current
    git pull origin main
    git rev-parse --short HEAD

    python manage.py check --settings=CONFIGURACION_ACTIVA
    python manage.py showmigrations revisiones --settings=CONFIGURACION_ACTIVA
    python manage.py migrate --settings=CONFIGURACION_ACTIVA

Esta entrega no agrega migraciones. El servidor puede tener pendientes las
0012 a 0015 de las entregas anteriores; showmigrations permite comprobarlo.

## Sincronización y comparación

Si corresponde renovar los datos del piloto, ejecutar:

    python manage.py sincronizar_odts --con-coordinadores --settings=CONFIGURACION_ACTIVA
    python manage.py estado_sincronizacion --settings=CONFIGURACION_ACTIVA
    python manage.py diagnosticar_calendario --mes 2026-11 --comparar-origen --settings=CONFIGURACION_ACTIVA

La proyección de responsables necesita renovarse periódicamente; esta guía no
configura el timer. La carga inicial debe terminar antes de evaluar su uso local.
No asumir que las visitas siguen siendo 76: comparar con el origen del momento.

## Aceptación funcional

| Área | Comprobar |
|---|---|
| Acceso | Admin y coordinador acceden con sus permisos; una sesión cerrada no sigue accediendo |
| Bandeja | Filtros, selección vacía, búsqueda, 50 filas, páginas siguientes y regreso conservan selección; detalle preventivo conserva su página independiente y ancla |
| Coordinadores | Solo ODT propias; una URL manipulada no amplía alcance |
| Catálogos | Servicios originales/corregidos y estados aparecen; responsables nuevos activos se pueden seleccionar |
| Correcciones | Revisar monto cero y servicio corregido; coordinador solo marca Procesada sobre ODT propias. No se asigna Actualizada manualmente. Usar registros de prueba |
| Calendario | Visitas realizadas, abiertas y atrasadas; servicios y búsqueda; cantidades disponibles y filtradas |
| Preventivos/análisis | Fechas, clasificación y enlaces se mantienen |
| Mensajes | Confirmaciones visibles una vez, errores diferenciados y sin HTML ejecutable |
| PDF | Contratista, período, requisición, ODT, CECO, tipo cliente, montos e historial |
| ZIP | Solo contratistas seleccionados; un PDF por contratista, sin mezclar ODT |
| Datos bancarios | Visibles únicamente con el permiso correspondiente |

Para probar escritura, utilizar registros de prueba identificados y registrar
valores iniciales y finales. No confirmar facturaciones ni eliminar períodos
reales como parte de una comprobación exploratoria.

## Evidencia de resultados

Anotar commit, módulo de configuración utilizado (sin secretos), usuario/rol,
filtros, hora, cantidades y cualquier error observado.
Comparar PC y servidor con los mismos filtros y versión; los cambios locales de
cada base no se trasladan con git pull ni con la sincronización de SoftGuard.

Registrar tiempos de las páginas y de exportación y el consumo de memoria.
La prueba con varios usuarios debe realizarse después de la prueba individual.
Una discrepancia no se corrige sobrescribiendo la base: primero identificar
ODT, diferencias del origen y correcciones locales.

Respaldos/restauración, protección del repositorio, configuración final y
traslado corporativo siguen siendo etapas pendientes. No se declaran
verificados por esta guía.

## Medición individual reproducible

Consultar DIAGNOSTICO_RENDIMIENTO.md para medir una lectura de bandeja con los mismos filtros en PC y servidor. El comando no mide peticiones concurrentes ni la RAM total. Empezar con una repetición y conservar commit y parámetros junto al resultado.

Si la primera medición es lenta, repetir con --sin-traza-memoria --detalle para separar etapas y lecturas directas del origen. No sumar etapas anidadas; comparar parámetros y versión idénticos.
