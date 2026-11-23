# Calendario de internos Santiago y Viña

El grupo `Calendario internos Santiago y Viña` restringe el calendario al técnico
actual `T. INTERNO - ServicioStgo` o `T. INTERNO - ServicioViña`. Se aplica en
servidor antes de contar, buscar, obtener servicios (también JSON) y renderizar.
No se utiliza el contratista como alternativa a un técnico vacío. Otros usuarios
mantienen su alcance actual. Se intersecta con el alcance de coordinador si existe.

## Activación en Raspberry

Integrar el PR, actualizar código y ejecutar:

```bash
cd /home/tamara/gestion-sstt-prueba
source .venv/bin/activate
git pull --ff-only
python manage.py check --settings=config.settings_prueba
python manage.py habilitar_calendario_internos --usuario calvarez --settings=config.settings_prueba
sudo systemctl restart sstt-prueba
sudo systemctl is-active sstt-prueba
```

Crear primero calvarez en Administración / Usuarios si no existe, activo, sin
staff, superusuario ni otros grupos, con contraseña privada. El comando no crea
usuarios ni cambia contraseñas; rechaza otros roles o permisos sin quitarlos.
Solo añade el grupo restringido y es idempotente. No requiere migraciones ni
publicar estáticos. No modifica ODT, pagos, informes, facturas ni acceso de Jair.

Comprobar con calvarez: inicio redirige al calendario, eventos, servicios y
contadores solo de ambos internos, sin acceso a gestión de pagos ni edición.
Comprobar que Jair conserva su acceso. No añadir otros roles si se desea mantener
consulta exclusiva del calendario. Asignar este grupo por admin restringe las
visitas pero no elimina permisos de otros grupos; el comando valida exclusividad.
