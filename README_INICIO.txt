SISTEMA SSTT - PRIMER PROTOTIPO DJANGO
====================================
Este proyecto funciona LOCALMENTE y usa ODT FICTICIAS.
NO está conectado a SQL Server y NO debe usarse para autorizar pagos reales.

REQUISITOS
- Windows 11
- Python instalado y accesible con el comando py
- Internet para instalar Django

PASO 1 - Extrae el ZIP en una carpeta, por ejemplo C:\SSTT\sstt_django
PASO 2 - Abre PowerShell en la carpeta que contiene manage.py
PASO 3 - Ejecuta los siguientes comandos, UNO POR UNO:

py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py makemigrations revisiones
python manage.py migrate
python manage.py createsuperuser
python manage.py cargar_demo
python manage.py runserver

PASO 4 - Abre http://127.0.0.1:8000/
La aplicación pedirá iniciar sesión. Utiliza el usuario y contraseña
que creaste con 'createsuperuser'.

Si PowerShell impide activar el entorno, puedes ejecutar sin activarlo:
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py makemigrations revisiones
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py cargar_demo
.\.venv\Scripts\python.exe manage.py runserver

PARA DETENER EL SERVIDOR: Ctrl+C

QUÉ FUNCIONA
- Inicio de sesión con usuarios Django
- Bandeja y filtros por contratista, estado de SoftGuard y estado de revisión
- Selección múltiple y cambio de estado con confirmación
- Comentario obligatorio para observar o rechazar
- Ficha de ODT e historial de cambios
- Persistencia de revisiones en SQLite

QUÉ FALTA
- Conexión SQL Server DW_Reporting (aún pendiente de Informática)
- Catálogos reales de contratistas, CECO, B2B/B2C y tarifas
- Reglas de negocio y aprobación de montos
- Períodos, cierres y exportación de pagos
- Seguridad y despliegue corporativo

IMPORTANTE
La base de datos SQLite se crea en db.sqlite3, en la misma carpeta.
No publiques este prototipo en internet. La clave de Django, DEBUG,
permisos y otros ajustes son SOLO para desarrollo local.
