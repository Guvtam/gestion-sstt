from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command

from revisiones.casos_uso.sincronizacion import ejecutar_sincronizacion
from revisiones.integraciones.bloqueo_sync import SincronizacionEnCurso
from revisiones.servicios_sql import iterar_odts_completas


class Command(BaseCommand):
    help = "Sincroniza ODT desde SQL Server por lotes, con historial y exclusión de procesos"

    def add_arguments(self, parser):
        parser.add_argument("--con-coordinadores", action="store_true", help="Renueva responsables locales después de importar las ODT")
        parser.add_argument("--simular", action="store_true", help="No escribe datos ni historial en la base local")
        parser.add_argument("--tamano-lote", type=int, default=250, help="Filas por lote, entre 1 y 1000")

    def handle(self, *args, **options):
        tamano = options["tamano_lote"]
        if not 1 <= tamano <= 1000:
            raise CommandError("El tamaño del lote debe estar entre 1 y 1000.")
        self.stdout.write("Consultando ODT desde SQL Server por lotes...")
        try:
            resultado = ejecutar_sincronizacion(
                lambda: iterar_odts_completas(tamano_lote=tamano),
                simular=options["simular"], tamano_lote=tamano,
                progreso=lambda r: self.stdout.write(f"Procesadas {r.consultadas} ODT..."),
            )
        except SincronizacionEnCurso as exc:
            raise CommandError(str(exc)) from None
        except KeyboardInterrupt:
            raise CommandError("Sincronización interrumpida. Consulta estado_sincronizacion antes de reintentar.") from None
        except Exception as exc:
            # No imprimir excepciones del driver: pueden contener datos de conexión.
            raise CommandError(
                f"La sincronización falló ({type(exc).__name__}). "
                "Consulta estado_sincronizacion. Los lotes anteriores confirmados se conservan."
            ) from None
        if options["simular"]:
            self.stdout.write(self.style.WARNING("SIMULACIÓN: no se guardaron datos ni historial."))
        elif resultado.omitidas:
            self.stdout.write(self.style.WARNING("Sincronización completada con omisiones; revisar el origen."))
        self.stdout.write(
            f"ODT consultadas: {resultado.consultadas}\n"
            f"ODT creadas: {resultado.creadas}\n"
            f"ODT actualizadas: {resultado.actualizadas}\n"
            f"ODT sin cambios: {resultado.sin_cambios}\n"
            f"ODT omitidas: {resultado.omitidas}\n"
            f"Cuentas incorporadas: {resultado.cuentas_incorporadas}\n"
            f"Equivalencias vinculadas: {resultado.equivalencias_creadas}"
        )
        if options["con_coordinadores"] and not options["simular"]:
            self.stdout.write("ODT sincronizadas. Renovando responsables locales...")
            call_command("sincronizar_coordinadores", stdout=self.stdout, stderr=self.stderr)
