# Varias requisiciones por contratista y período

## Comportamiento

Cada confirmación crea una facturación independiente por contratista con las ODT
previsualizadas todavía pendientes. Si ya existe una requisición del mismo
contratista/período, no se reutiliza, sobrescribe ni se le anexan nuevas ODT.

Ejemplo en el período 21/10–20/11:

| Registro | Servicio | ODT | Monto | Requisición |
|---|---|---:|---:|---|
| Anterior | Nueva instalación | 2 | $250.000 | 4830 |
| Nuevo | Correctivas y renovación | 5 | $150.500 | Nuevo número, por ejemplo 4832 |

El formulario siempre presenta un campo nuevo y vacío de requisición. Informa
si existen facturaciones anteriores del contratista, sin autocompletar su número.
Como antes, el número puede quedar pendiente y completarse desde el historial.
Se permiten varias facturaciones pendientes con número vacío; cada una mantiene
su propio identificador. Un número informado no puede repetirse para el mismo
contratista y período; sí puede coincidir en otro período o contratista.

El historial muestra una fila por facturación, su requisición, ODT, monto, fecha
y registro. El contador de contratistas del período cuenta nombres distintos,
no facturaciones. Ver ODT, búsqueda y auditoría apuntan al registro concreto.
La descarga ZIP produce un PDF independiente por facturación/requisición, incluso
si se seleccionan varias del mismo contratista. El archivo identifica requisición
y registro para evitar colisiones, también si el número está pendiente.
El informe consolidado por períodos conserva cada requisición y suma sus ODT una
sola vez.

## Protecciones conservadas

- OneToOne de FacturacionODT.odt: una ODT no puede facturarse dos veces.
- Misma huella y CAMPOS, aprobación efectiva, fechas, filtros y montos revisados.
- Confirmación firmada y relectura con bloqueo dentro de transacción. Se cambia
  la versión/salt a v2 para rechazar formularios abiertos antes de esta entrega:
  recargar previsualización, sin escrituras parciales.
- Cabeceras, items y auditoría nuevos se confirman o revierten juntos.
- Servicio/monto facturados y contratista de las facturaciones emitidas permanecen
  intactos. No se divide ni reconstruye automáticamente un histórico mixto.
- Yasna solo factura instalación genérica, excluyendo Cruzverde. Solo ve items
  autorizados por instantánea. No edita una requisición de otros servicios ni una
  cabecera histórica mixta; sus nuevos grupos puros sí son independientes.
- Datos bancarios mantienen el permiso específico existente; no cambia el contenido
  autorizado del PDF. La selección de cabeceras sin ODT autorizadas se rechaza.

## Migración 0017

Reemplaza la unicidad (período, contratista) por una unicidad condicional sobre
(período, contratista, número de requisición), solo si el número no está vacío.
No agrega campos ni ejecuta migraciones de datos. Conserva PK, requisiciones,
items, instantáneas y eventos; la restricción OneToOne de ODT permanece.

La migración se probó desde 0016 con facturación, item y auditoría existentes,
verificando conservación de sus identificadores y valores y la posibilidad de
registrar otra requisición después.

No revertir solo el código ni ejecutar migrate a 0016 después de registrar varias
facturaciones del mismo contratista/período: el esquema anterior no las admite.
Una vuelta atrás requiere un plan de restauración consistente de código y datos,
sin perder facturaciones posteriores al respaldo.

## Prueba local aislada

Con el entorno virtual activado, desde la copia sstt-prueba-visual, detener el
servidor con Ctrl+C. Crear un respaldo SQLite consistente de esa copia:

```powershell
New-Item -ItemType Directory -Force ..\respaldo-sstt-visual
python manage.py shell --settings=config.settings_visual -c "from pathlib import Path; from django.utils import timezone; from revisiones.management.commands.reparar_contratistas_odt import respaldar_sqlite; print(respaldar_sqlite(Path('../respaldo-sstt-visual') / ('antes_requisiciones_' + timezone.now().strftime('%Y%m%d_%H%M%S') + '.sqlite3')))"
```

Solo si terminó correctamente:

```powershell
git fetch origin
git switch --detach origin/mejora/requisiciones-multiples
python manage.py migrate --settings=config.settings_visual
python manage.py runserver 127.0.0.1:8001 --settings=config.settings_visual
```

Probar el ejemplo en la copia; comprobar dos filas, totales separados, búsquedas,
PDFs y alcance de Yasna. No hacer pruebas ficticias de facturación sobre la base
activa de la Raspberry. El PR se entrega en borrador; no despliega automáticamente.

## Despliegue posterior en Raspberry

Una vez integrada la rama, usar config.settings_prueba, nunca settings_visual.
Revisar git status y detenerse si hay modificaciones; hacer respaldo verificado de
la base activa con respaldar_sqlite, como en docs/OPERACION.md. Pausar la
sincronización programada con el mecanismo configurado en el servidor y detener
sstt-prueba durante la actualización. No sustituir la base por la del PC.

Después del respaldo y con escritores detenidos, actualizar main, ejecutar:

```bash
python manage.py migrate --plan --settings=config.settings_prueba
python manage.py migrate --settings=config.settings_prueba
python manage.py check --settings=config.settings_prueba
python manage.py collectstatic --noinput --settings=config.settings_prueba
sudo cp -R /home/tamara/sstt-datos-prueba/static/. /var/www/sstt-prueba/static/
sudo systemctl start sstt-prueba
sudo systemctl is-active sstt-prueba
```

Si hay error, detener el procedimiento sin confirmar nuevas facturaciones.
Reanudar sincronización tras migración correcta y servicio activo. Recargar las
previsualizaciones de facturación abiertas antes de la actualización.
