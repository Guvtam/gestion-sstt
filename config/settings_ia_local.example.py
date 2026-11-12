"""Copiar a settings_ia_local.py para pruebas EXCLUSIVAMENTE en 127.0.0.1."""
import os
from .settings import *  # noqa: F403

# Después de cargar settings, para no usar la clave de desarrollo del proyecto.
SECRET_KEY = os.environ['SSTT_IA_LOCAL_SECRET_KEY']
DEBUG = False
ALLOWED_HOSTS = ['127.0.0.1', 'localhost']
