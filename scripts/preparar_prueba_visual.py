"""Clonar SQLite por su API de backup. No cambia Git, la base original ni el servidor."""
from contextlib import closing
import argparse
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import subprocess


def copiar_base(origen, destino):
    origen, destino = Path(origen).resolve(), Path(destino).resolve()
    if not origen.is_file():
        raise ValueError('No se encontró la base local de origen; no se creará una base vacía.')
    if origen == destino or destino.exists():
        raise ValueError('El destino ya existe. Se conserva: usa otra carpeta para una nueva prueba.')
    # mode=ro impide crear o escribir el origen, incluso si se equivoca la ruta.
    try:
        with closing(sqlite3.connect(origen.as_uri()+'?mode=ro', uri=True)) as fuente:
            with closing(sqlite3.connect(destino)) as copia:
                fuente.backup(copia)
                if copia.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('La verificación de integridad de la copia no fue correcta.')
    except Exception:
        destino.unlink(missing_ok=True)
        raise
    return destino


def preparar_esquema(destino):
    """Aplicar migraciones del código únicamente a la base aislada de la prueba."""
    destino = Path(destino).resolve()
    if not (destino/'config/settings_visual.py').is_file() or not (destino/'db_visual.sqlite3').is_file():
        raise ValueError('Falta la carpeta de prueba o su copia de base; no se ejecutarán migraciones.')
    subprocess.run([sys.executable, str(destino/'manage.py'), 'migrate', '--noinput',
                    '--settings=config.settings_visual'], cwd=destino, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origen', required=True, help='Carpeta donde usas actualmente el sistema en tu PC.')
    parser.add_argument('--destino', required=True, help='Nueva carpeta creada con git worktree.')
    parser.add_argument('--settings', default=os.environ.get('DJANGO_SETTINGS_MODULE', 'config.settings'))
    args = parser.parse_args()
    origen, destino = Path(args.origen).resolve(), Path(args.destino).resolve()
    if origen == destino or not (origen/'manage.py').is_file() or not (destino/'config/settings_visual.py').is_file():
        parser.error('Selecciona la carpeta habitual y una carpeta de prueba distinta con settings_visual.py.')
    sys.path.insert(0, str(origen))
    os.environ['DJANGO_SETTINGS_MODULE'] = args.settings
    from django.conf import settings
    base = settings.DATABASES['default']
    if base['ENGINE'] != 'django.db.backends.sqlite3':
        parser.error('Esta preparación local requiere SQLite; no se conectará a otra base.')
    try:
        copia = copiar_base(base['NAME'], destino/'db_visual.sqlite3')
        entorno = origen/'config/.env'
        if entorno.is_file():
            shutil.copy2(entorno, destino/'config/.env')
    except (ValueError, sqlite3.Error, OSError) as error:
        parser.error(str(error))
    print('Copia de prueba creada y verificada:', copia.name)
    print('Aplicando migraciones pendientes solo en la copia visual…', flush=True)
    try:
        preparar_esquema(destino)
    except (ValueError, subprocess.CalledProcessError) as error:
        parser.error('La copia se creó, pero falta completar su esquema. Desde la carpeta de prueba ejecuta:\n'
                     'python manage.py migrate --settings=config.settings_visual')
    print('La base original y la Raspberry permanecen sin cambios.')


if __name__ == '__main__':
    main()
