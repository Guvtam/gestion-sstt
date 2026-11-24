# Detalle técnico desde el calendario de internos

Los miembros del grupo `Calendario internos Santiago y Viña` con permiso activo
`ver_calendario_sstt` pueden pulsar una visita para consultar su detalle técnico.
No depende del nombre calvarez ni de excepciones por usuario. El usuario ya
habilitado con `habilitar_calendario_internos` no requiere nuevos permisos.

Ruta exclusiva GET `/calendario-servicios/odt/<numero>/`, distinta del detalle
operativo y del JSON de historial financiero existentes. Comprueba de nuevo el
alcance por técnico actual, fecha de visita no vacía y estados de visita válidos;
si hay alcance de coordinador se intersecta. ODT ajenas o reasignadas a externos
responden 404 antes de consultar SQL. Sin acceso al grupo/permiso responde 403.
No amplía el acceso de Jair ni modifica sus enlaces actuales.

Muestra cuenta, dirección, localidad, técnico, estado SoftGuard, servicio efectivo,
fechas, observaciones e historial del origen con fecha, acción y nombre de usuario.
Solo pasa al template una proyección explícita de campos; no pasa el modelo ODT,
montos, revisión de pago, facturas, datos bancarios, correos ni auditorías locales
financieras. No expone funciones de edición ni concede permisos de escritura.

El historial y observaciones de origen son texto libre: los fragmentos con
monedas, importes con separadores y términos administrativos identificables se
sustituyen por `[Contenido administrativo omitido]`; acciones financieras se
excluyen. Esto es un filtro de texto conservador, no una clasificación semántica
infalible de importes sin contexto; revisar las convenciones de registro del
origen si contienen nuevos formatos. Los textos técnicos restantes se muestran
escapados, sin ejecutar HTML. Ante fallo SQL se conserva el detalle y se informa
que el historial no está disponible, sin errores internos ni datos de conexión.

Volver al calendario conserva mes/filtros. Solo acepta ruta relativa del propio
calendario, nunca destinos externos o acciones. Respuesta sin almacenamiento en
caché para evitar reutilizar datos después de cambiar de usuario o alcance.

## Despliegue

Tras integrar el PR en main, en Raspberry:

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

No requiere migraciones, reconfigurar perfiles ni cambiar datos del usuario.
Probar como calvarez: pulsar una visita interna, revisar historial y regresar;
abrir directamente un número externo debe denegarse. Los accesos anteriores a
pagos, revisión, informes y facturación siguen denegados. Si SQL no responde,
la página sigue mostrando los datos técnicos locales y un aviso de historial.
