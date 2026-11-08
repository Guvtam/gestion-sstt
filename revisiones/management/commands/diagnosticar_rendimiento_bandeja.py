"""Medición individual del adaptador de lectura, sin sesión persistida ni SQL escrito."""
from contextlib import ExitStack, redirect_stdout
from datetime import date
from io import StringIO
from time import perf_counter
import tracemalloc

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import PermissionDenied
from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.test import RequestFactory

from revisiones.dominio.servicios import SERVICIOS_PRINCIPALES
from revisiones.vistas.bandeja import bandeja


class SoloLecturaRequerida(RuntimeError):
    pass


def medir_peticion(request, *, por_creacion=False):
    consultas = 0
    tiempo_sql = 0.0

    def observar(execute, sql, params, many, context):
        nonlocal consultas, tiempo_sql
        if not sql.lstrip().upper().startswith("SELECT"):
            raise SoloLecturaRequerida("La medición no admite sentencias distintas de SELECT.")
        consultas += 1
        inicio = perf_counter()
        try:
            return execute(sql, params, many, context)
        finally:
            tiempo_sql += perf_counter() - inicio

    traza_propia = not tracemalloc.is_tracing()
    if traza_propia:
        tracemalloc.start()
    try:
        inicio = perf_counter()
        with ExitStack() as stack:
            for conexion in connections.all():
                stack.enter_context(conexion.execute_wrapper(observar))
            # Evita mezclar los prints diagnósticos de la vista con este informe.
            with redirect_stdout(StringIO()):
                respuesta = bandeja(request, por_creacion=por_creacion)
            if hasattr(respuesta, "render") and not respuesta.is_rendered:
                respuesta.render()
        segundos = perf_counter() - inicio
        pico = tracemalloc.get_traced_memory()[1] if traza_propia else None
        return {
            "estado": respuesta.status_code, "segundos": segundos,
            "consultas": consultas, "segundos_sql": tiempo_sql,
            "pico_python_bytes": pico, "respuesta_bytes": len(respuesta.content),
        }
    finally:
        if traza_propia:
            tracemalloc.stop()


class Command(BaseCommand):
    help = "Mide una lectura de bandeja; no simula Nginx, red ni concurrencia"

    def add_arguments(self, parser):
        parser.add_argument("--usuario", required=True)
        parser.add_argument("--fecha-desde", required=True)
        parser.add_argument("--fecha-hasta", required=True)
        parser.add_argument("--por-creacion", action="store_true")
        parser.add_argument("--estado")
        grupo = parser.add_mutually_exclusive_group()
        grupo.add_argument("--servicio", action="append")
        grupo.add_argument("--todos-servicios", action="store_true")
        parser.add_argument("--contratista", action="append")
        parser.add_argument("--pagina", type=int, default=1)
        parser.add_argument("--repeticiones", type=int, default=1)

    def handle(self, *args, **options):
        try:
            desde = date.fromisoformat(options["fecha_desde"])
            hasta = date.fromisoformat(options["fecha_hasta"])
            if desde > hasta:
                raise ValueError
        except ValueError:
            raise CommandError("Usa fechas válidas AAAA-MM-DD en orden ascendente.") from None
        if not 1 <= options["repeticiones"] <= 3 or options["pagina"] < 1:
            raise CommandError("Admite una página positiva y entre 1 y 3 repeticiones.")
        datos = {"fecha_desde": desde.isoformat(), "fecha_hasta": hasta.isoformat(),
                 "page": str(options["pagina"])}
        if options["estado"] is not None:
            datos["estado"] = options["estado"]
        if options["servicio"] is not None:
            datos["servicios"] = options["servicio"]
        elif not options["por_creacion"] and not options["todos_servicios"]:
            datos["servicios"] = list(SERVICIOS_PRINCIPALES)
        if options["contratista"] is not None:
            datos["contratista"] = options["contratista"]
            datos["contratistas_filtrados"] = "1"
        for n in range(1, options["repeticiones"] + 1):
            try:
                # Instancia nueva por repetición: sin permisos/cache heredados de la anterior.
                usuario = get_user_model().objects.get(username=options["usuario"], is_active=True)
            except get_user_model().DoesNotExist:
                raise CommandError("Selecciona un usuario activo existente.") from None
            request = RequestFactory().get("/", datos)
            request.user = usuario
            request.session = {}
            request._messages = FallbackStorage(request)
            try:
                resultado = medir_peticion(request, por_creacion=options["por_creacion"])
            except PermissionDenied:
                raise CommandError("El usuario no tiene acceso a la bandeja solicitada.") from None
            except Exception as error:
                raise CommandError(
                    f"No se pudo completar la medición ({type(error).__name__}). "
                    "No se imprime HTML, SQL ni información de conexión."
                ) from None
            pico = resultado["pico_python_bytes"]
            memoria = f"{pico / 1024**2:.2f} MiB" if pico is not None else "No disponible: traza previa activa"
            self.stdout.write(
                f"Medición {n}: HTTP {resultado['estado']} | Tiempo: {resultado['segundos']:.3f} s | "
                f"Consultas Django: {resultado['consultas']} | Tiempo SQL Django: {resultado['segundos_sql']:.3f} s\n"
                f"Pico de asignaciones Python: {memoria} | Respuesta: {resultado['respuesta_bytes']} bytes"
            )
        self.stdout.write(
            "Incluye sobrecarga de instrumentación. No mide RAM total, Nginx, navegador ni concurrencia. "
            "Las consultas pyodbc no se cuentan como consultas Django."
        )
