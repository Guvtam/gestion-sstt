# Gestión SSTT

Aplicación Django para revisar ODT, gestionar pagos y facturación, consultar
preventivos y analizar servicios. SoftGuard se consulta mediante SQL Server;
las revisiones, correcciones, contratistas y facturaciones se guardan en la
base de datos de la aplicación.

## Estado del proyecto

Piloto en Raspberry Pi con Nginx, Gunicorn y configuración local
`config.settings_prueba`. Este archivo y la base del piloto no deben
reemplazarse al actualizar el código. La configuración principal todavía
requiere endurecimiento antes del despliegue corporativo.

- [Revisión técnica y prioridades](docs/REVISION_TECNICA.md)
- [Arquitectura propuesta](docs/ARQUITECTURA.md)
- [Reestructuración implementada y siguientes etapas](docs/REESTRUCTURACION.md)
- [Operación, respaldos y traslado](docs/OPERACION.md)

El archivo `README_INICIO.txt` corresponde al prototipo original y queda
como referencia histórica. No seguir sus instrucciones para operar el piloto:
el sistema actual sí tiene conexión SQL y datos persistentes.

## Entorno de desarrollo y pruebas

Python 3.13. Crear un entorno virtual e instalar:

```bash
python -m venv .venv
# Linux:
source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python manage.py check --settings=config.settings_test
python manage.py makemigrations --check --dry-run --settings=config.settings_test
python manage.py test contratistas revisiones --settings=config.settings_test
```

En Linux, `pyodbc` necesita las bibliotecas de unixODBC. Para conectarse al
origen también se necesita Microsoft ODBC Driver 18; las pruebas simuladas no
lo necesitan. `settings_test` usa SQLite en memoria y no carga archivos `.env`.
No utilizar esta configuración para servir usuarios: usa un hash de contraseña
rápido destinado exclusivamente a pruebas.

Los paquetes de ejecución están en `requirements.txt`; las herramientas de
prueba en `requirements-dev.txt`; Gunicorn se agrega con
`requirements-server.txt`. Los rangos declarados no son un archivo de bloqueo
de versiones. Registrar y validar versiones exactas antes de cada release.

## Reglas que deben preservarse

- Gestión de pagos: fecha de finalización y estado Finalizado por defecto.
- ODT por creación: fecha de creación, incluyendo servicios sin técnico.
- Coordinadores: solo sus ODT identificadas y operaciones autorizadas.
- Una cuenta con código válido sin clasificación explícita se considera B2C.
  Sin código reconocible se muestra Sin clasificar; CECO no se infiere.
- Una ODT facturada conserva servicio y monto facturados como instantánea.
- Procesada es una marca manual; Actualizada requiere coincidencia con el origen.
- Visitas: fecha de visita; realizadas en azul, abiertas en verde y atrasadas
  en amarillo.

## Actualizaciones del piloto

No copiar bases desde GitHub ni desde el PC sobre la base de la Raspberry.
Respaldar y verificar la configuración activa antes de ejecutar migraciones.
No ejecutar `cargar_demo` ni `makemigrations` en el servidor del piloto.
Consultar el procedimiento de [operación](docs/OPERACION.md).
