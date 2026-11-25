# Prueba local: identidad, incidencias y exportaciones

Esta rama se revisa primero en el PC. No requiere migraciones, cambios de permisos,
merge a main ni actualización de la Raspberry. Conserva las reglas de pagos,
rechazos, facturación, revisión y sincronización existentes.

## Abrir una copia independiente en Windows (PowerShell)

Desde tu carpeta habitual del sistema, con el entorno virtual activado, ejecuta:

```powershell
git fetch origin
git worktree add --detach ..\sstt-prueba-visual origin/prueba/identidad-incidencias-exportaciones
python ..\sstt-prueba-visual\scripts\preparar_prueba_visual.py --origen . --destino ..\sstt-prueba-visual
cd ..\sstt-prueba-visual
python manage.py runserver 127.0.0.1:8001 --settings=config.settings_visual
```

Abre http://127.0.0.1:8001 e ingresa con tu usuario habitual. La sesión, base y
configuración corresponden al PC, no al servidor. El script obtiene la ruta de
SQLite desde tu configuración habitual, hace una copia con la API de backup,
verifica integridad y copia `config/.env` local sin mostrar su contenido. Si tu
PC usa otro módulo de configuración, agrega `--settings=config.TU_MODULO` al
comando del script, no al comando de runserver.

`settings_visual` obliga a usar `db_visual.sqlite3` en la nueva carpeta y permite
acceso únicamente por localhost. No sobrescribe tu `db.sqlite3`, configuraciones
ni cambios pendientes del proyecto habitual. No ejecutes sincronizaciones para
esta revisión visual. La copia contiene los mismos datos privados del PC: no
subas bases, .env ni exportables al repositorio.

Si la carpeta o la copia ya existe, no vuelvas a prepararla sobre la misma. Para
continuar una prueba ya preparada, usa solo los dos últimos comandos. No uses
`git reset --hard`, no cambies el servicio ni hagas pull en la Raspberry.

## Qué comprobar

- Identidad: entrada, bandeja, calendarios, análisis, cuentas, contratistas,
  facturación, detalle y administración. Logo original; naranja, negro y grises.
  Los colores de estados (SLA, rechazo, incidencias y calendario) se mantienen.
- Incidencias: una columna con 90 / 60 / 30 días en horizontal. Son acumulativas:
  por ejemplo 13 / 8 / 5. Conservan misma cuenta exacta + contratista, estado
  finalizado y fecha de finalización dentro de cada ventana móvil hasta hoy.
  Incluyen la ODT actual si cumple esos criterios; no usan la fecha del filtro
  como extremo de la ventana ni cambian los umbrales de severidad.
- Juan Pablo (`jiturriaga`): FDP, fallo de prueba y fallo de comunicación se
  detectan dentro del texto, con cualquier combinación de mayúsculas, tildes y
  espacios. Aparecen al final del conjunto filtrado antes de paginar. Verde
  suave; cuando existe destacado naranja se conserva el naranja y se agrega
  una marca verde. Los demás usuarios mantienen su orden y presentación.
  El retorno inmediato de un guardado sigue conservando la página y posición.
- Bandeja: selecciona ODT con casillas, cambia de página con los mismos filtros
  y exporta Excel/PDF. El encabezado selecciona solo la página visible; el
  contador incluye selecciones de otras páginas. Cambiar filtros inicia otra
  selección; Limpiar selección borra la del contexto actual. Máximo 2.000 ODT.
  Los archivos incluyen observaciones completas, responsables, CECO, tipo de
  cliente, fechas, SLA, incidencias y montos originales/efectivos. Un Excel que
  exceda el límite de texto de una celda se rechaza: usar PDF en ese caso.
- Calendario: Exportar PDF con estos filtros genera agenda mensual y detalle
  de visitas. Respeta mes, servicio, búsqueda, categoría y técnicos autorizados.
- Análisis ODT y coordinadores: Exportar PDF con estos filtros genera indicadores
  y detalle de todas las páginas, hasta 10.000 filas. Son informes tabulares,
  no capturas de gráficos. El análisis por coordinador conserva su criterio:
  carga total del período y correcciones según sus propios filtros.
- Facturación: marca uno o varios períodos en la tabla superior y exporta PDF.
  El archivo reúne resumen y detalle de la facturación visible para tu perfil,
  con servicio/monto facturados, contratista y requisición históricos. Máximo
  120 períodos y 10.000 ODT. No recalcula con los valores actuales de las ODT.
- Permisos: Cristian conserva únicamente técnicos internos Santiago/Viña.
  Yasna conserva exclusivamente nueva instalación genérica, excluye Cruzverde,
  también al exportar instantáneas facturadas. Los nuevos informes no incluyen
  datos bancarios; los PDF anteriores conservan su permiso bancario específico.

El servidor revalida toda selección contra filtros y permisos actuales. Una
selección que quedó fuera de alcance se rechaza completa; limpiar y seleccionar
nuevamente. Las descargas no cambian ODT, revisiones, informes ni facturas.

## Verificaciones automatizadas

```powershell
python manage.py check --settings=config.settings_test
python manage.py makemigrations --check --dry-run --settings=config.settings_test
python manage.py test contratistas revisiones --settings=config.settings_test
```

Para finalizar la prueba local, presiona Ctrl+C. Tu copia habitual y el servidor
continúan en su versión anterior. Validar visualmente en el navegador del PC
antes de decidir un despliegue; los tests no sustituyen esa revisión.
