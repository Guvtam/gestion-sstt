from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

import os
from dotenv import load_dotenv

load_dotenv(BASE_DIR / "config" / ".env", override=True)

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY", "desarrollo-local-cambiar-antes-de-publicar"
)
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = ["127.0.0.1", "localhost","192.168.1.209"]
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "revisiones",
    "contratistas",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "revisiones.acceso_coordinadores.AccesoCoordinadorMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
DATABASES = {
    "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}
}
AUTH_PASSWORD_VALIDATORS = []
LANGUAGE_CODE = "es-cl"
TIME_ZONE = "America/Santiago"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/admin/login/"
THOUSAND_SEPARATOR = "."

DECIMAL_SEPARATOR = ","

USE_THOUSAND_SEPARATOR = True

load_dotenv(BASE_DIR / ".env")

# Conexion SQL Server - Base de exploracion
SQL_EXPLORACION = {
    "SERVER": os.getenv("SQL_SERVER"),
    "PORT": os.getenv("SQL_PORT", "1433"),
    "DATABASE": os.getenv("SQL_DATABASE"),
    "USER": os.getenv("SQL_USER"),
    "PASSWORD": os.getenv("SQL_PASSWORD"),
}



# AUTENTICACIÓN SSTT

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "bandeja"
LOGOUT_REDIRECT_URL = "login"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SSTT_IMAGE_HOSTS = [
   "cli.firstsecurity.cl",
]