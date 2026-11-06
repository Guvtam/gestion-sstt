"""Exclusión entre procesos del mismo host; el SO libera al terminar el proceso."""
from contextlib import contextmanager
import errno
import os
from pathlib import Path

from django.conf import settings


class SincronizacionEnCurso(Exception):
    pass


def ruta_bloqueo():
    configurada = getattr(settings, "SSTT_SYNC_LOCK_FILE", None)
    if configurada:
        return Path(configurada).expanduser().resolve()
    base = settings.DATABASES["default"]
    nombre = str(base.get("NAME", ""))
    if base["ENGINE"].endswith("sqlite3") and nombre and nombre != ":memory:" and not nombre.startswith("file:"):
        return Path(nombre).expanduser().resolve().with_name(Path(nombre).name + ".sync.lock")
    return Path(getattr(settings, "BASE_DIR", Path.cwd())) / ".sstt-sync.lock"


@contextmanager
def bloquear_sincronizacion():
    ruta = ruta_bloqueo()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("a+b") as archivo:
        try:
            if os.name == "nt":
                import msvcrt
                if ruta.stat().st_size == 0:
                    archivo.write(b"0")
                    archivo.flush()
                archivo.seek(0)
                msvcrt.locking(archivo.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(archivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise SincronizacionEnCurso("Ya hay una sincronización ejecutándose.") from None
            raise
        try:
            yield
        finally:
            if os.name == "nt":
                archivo.seek(0)
                msvcrt.locking(archivo.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(archivo.fileno(), fcntl.LOCK_UN)
    # No borrar: otro proceso podría estar usando el mismo inode.
