# Resumen sin rechazados y reapertura de rechazos

## Resumen del período

Parte del mismo queryset autorizado y filtrado de la tabla, antes de paginar.
Excluye únicamente Revision.estado RECHAZADA, tanto cantidad como monto; mantiene
los otros estados. Por ello el encabezado dice Total sin rechazados y no Total
aprobado. Las tarjetas superiores conservan sus reglas y muestran por separado
los rechazados. La tabla de ODT conserva rechazados para poder revisarlos/reabrirlos.

B2B, B2C, Cruz Verde y Tattersall son categorías excluyentes del resumen. Las marcas
se identifican como antes por nombre de cuenta (Cruz Verde/Cruzverde y Tattersall);
Cruz Verde tiene precedencia ante un nombre que contenga ambas. No cambia el
catálogo de tipo de cliente, CECO ni las reglas de facturación por B2B/B2C. Si
existen ODT sin clasificar o servicios desconocidos se muestran para conciliar.

La fila inferior Total sin rechazados suma monto y ODT de cada servicio y total
general. Conserva importe efectivo y clasificación por servicio editado si existe,
incluidos el cero y la marca local 2. Los grupos y las columnas suman el mismo total.
No se implementa bloqueo de períodos ni conciliación diaria adicional.

## Deshacer rechazo

Acción separada en la fila rechazada y no facturada: Deshacer rechazo, motivo
obligatorio y Confirmar aprobación. Único destino APROBADA; no admite elegir
En revisión. Mantiene los filtros, página y posición usando el controlador de
retorno existente (si deja de cumplir un filtro, se informa que ya no aparece).
Cancelar o cerrar antes de confirmar no envía escritura.

POST reabrir-rechazo exige permiso operativo revisar_pago_sstt y CSRF. Valida
alcance adicional de nueva instalación para Yasna, bloqueo de facturación y estado
actual rechazado, bajo transacción y bloqueo del mismo ODT usado en facturación.
No otorga permisos a coordinadores ni calendario. Yasna conserva solo instalación
genérica y no Cruzverde ni otros servicios.

La edición, revisión normal y operaciones masivas siguen bloqueando rechazadas;
no se flexibiliza el cargador general de ODT editables. El endpoint específico
cambia únicamente Revision, guarda actor/fecha y crea EventoRevision de RECHAZADA
a APROBADA con motivo nuevo y motivo anterior para preservar casos legacy.
No cambia monto, servicio, informe, coordinador, corrección ni datos facturados.
Si falla la auditoría se revierte la reapertura. Repetir tras una reapertura responde
409 y no duplica el evento. El historial existente muestra la reapertura.

## Actualización Raspberry

Integrar el PR después de revisar CI. Este cambio no agrega migraciones; se parte
de la versión actual con 0016 del PR98 ya aplicada. Si falta esa actualización,
seguir primero docs/DETECCIONES_SOFTGUARD.md.

```bash
cd /home/tamara/gestion-sstt-prueba
source .venv/bin/activate
git pull --ff-only
python manage.py check --settings=config.settings_prueba
python manage.py collectstatic --noinput --settings=config.settings_prueba
sudo cp -R /home/tamara/sstt-datos-prueba/static/. /var/www/sstt-prueba/static/
sudo systemctl restart sstt-prueba
sudo systemctl is-active sstt-prueba
```

Ctrl+F5. No reset ni restauración de base. Comprobar totales con los mismos filtros,
registro de rechazo y ausencia de reapertura en una facturada. No reabrir una ODT
real como prueba: la confirmación la deja aprobada y elegible según las reglas
vigentes. Las pruebas automáticas usan base aislada y datos ficticios.
