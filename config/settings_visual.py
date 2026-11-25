"""Prueba local aislada; preparar primero la copia con preparar_prueba_visual.py."""
from .settings import *  # noqa: F403
from django.core.exceptions import ImproperlyConfigured

DEBUG = True
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '[::1]']
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db_visual.sqlite3'}}
if not DATABASES['default']['NAME'].is_file():
    raise ImproperlyConfigured('Falta db_visual.sqlite3. Ejecuta primero scripts/preparar_prueba_visual.py desde tu copia habitual.')
