from django.core.management.base import BaseCommand, CommandError
from revisiones.casos_uso.proyeccion_coordinadores import actualizar_proyeccion
from revisiones.integraciones.bloqueo_sync import bloquear_sincronizacion, SincronizacionEnCurso


class Command(BaseCommand):
    help = "Renueva responsables locales desde el origen, por lotes de hasta 250 ODT"

    def add_arguments(self, parser):
        parser.add_argument("--simular", action="store_true")
        parser.add_argument("--tamano-lote", type=int, default=250)

    def handle(self, *args, **options):
        if not 1 <= options["tamano_lote"] <= 250:
            raise CommandError("El lote debe estar entre 1 y 250.")
        try:
            with bloquear_sincronizacion():
                total = actualizar_proyeccion(tamano_lote=options["tamano_lote"], simular=options["simular"])
        except SincronizacionEnCurso as exc:
            raise CommandError(str(exc)) from None
        except Exception:
            raise CommandError("No se pudo completar la proyección. Los lotes confirmados se conservan; no se autoriza con datos caducados.") from None
        self.stdout.write(f"ODT verificadas: {total}" + (" (simulación, sin escritura)" if options["simular"] else ""))
