# Diagnóstico individual de bandeja

El comando ejecuta la lectura y renderizado de bandeja para un usuario activo
existente, con sus permisos. No inicia sesión ni guarda una sesión de Django.

    python manage.py diagnosticar_rendimiento_bandeja --usuario USUARIO_AUTORIZADO --fecha-desde 2026-10-21 --fecha-hasta 2026-11-06 --settings=CONFIGURACION_ACTIVA

CONFIGURACION_ACTIVA y USUARIO_AUTORIZADO son marcadores del despliegue.
En el PC puede omitirse --settings si se usa su configuración habitual.

## Parámetros y comparación

- Fechas obligatorias y ordenadas; página positiva.
- --por-creacion selecciona la bandeja por creación.
- --estado permite seleccionar estado; un valor vacío no impone estado.
- Pagos usa los cuatro servicios iniciales; creación no los impone.
- --servicio es repetible; --todos-servicios evita imponer los cuatro iniciales.
- --contratista es repetible; si se omite se usan las opciones disponibles.
- --pagina selecciona la página; --repeticiones admite de una a tres.
- Cada repetición carga una instancia nueva del usuario para evitar caché de
  permisos heredada de la repetición anterior.

Comparar mismo commit, rol, fechas, servicios, contratistas y página entre PC
y servidor. Las cachés de plantillas/base pueden calentarse entre repeticiones.
Una medición no permite concluir capacidad con siete usuarios.

## Qué mide

- Tiempo total del adaptador, incluyendo render y sobrecarga de instrumentación.
- Cantidad y tiempo de consultas ejecutadas por las conexiones Django.
- Pico de asignaciones Python durante la medición, cuando inicia su propia traza.
- Estado HTTP y cantidad de bytes de respuesta.

No mide RAM total/RSS, asignaciones nativas, navegador, Nginx, transporte HTTP,
middleware completo, arranque del proceso ni concurrencia.
Las consultas directas pyodbc no se cuentan como consultas Django; su espera
puede contribuir al tiempo total. El usuario se obtiene antes de cronometrar.

HTTP 200 no certifica disponibilidad del origen: la presentación administrativa
puede mostrar responsables no disponibles. Comprobar también la página y el
estado de sincronización.

## Lectura y límites

La medición utiliza GET y una sesión en memoria. Envuelve las conexiones Django
para bloquear sentencias que no comiencen por SELECT, antes de ejecutarlas.
No guarda texto SQL, parámetros, HTML ni datos de conexión en el informe.
No imprime mensajes internos del driver.

Esta protección del instrumento no reemplaza permisos de solo lectura del
origen ni analiza efectos de funciones SQL o conexiones externas. Se utiliza
exclusivamente con el adaptador de lectura revisado, no como sandbox SQL general.
La traza de memoria añade sobrecarga; sus números son orientativos.

No modifica índices, configuración, timer o datos del despliegue.
No requiere migraciones ni sincronización adicional.

## Validación

419 pruebas correctas, check sin incidencias y sin migraciones pendientes.
Regresiones nuevas verifican render real sin sesión persistida, parámetros,
usuario activo/permisos, filtros, repeticiones, bloqueo de escritura, limpieza
de instrumentación y errores sin datos del driver.

No se ejecutó el diagnóstico sobre el PC de la usuaria o el servidor.
Los resultados reales deben obtenerse allí antes de decidir optimizaciones.
