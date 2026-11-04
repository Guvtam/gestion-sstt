
from django.core.management.base import BaseCommand
from django.db import transaction

from revisiones.models import ODT, CatalogoCuenta
from revisiones.cuentas_utils import normalizar_codigo_cuenta


class Command(BaseCommand):
    help = "Incorpora cuentas faltantes desde las ODT, sin modificar las existentes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--simular",
            action="store_true",
            help="Muestra resultados sin guardar cambios.",
        )

    def handle(self, *args, **options):
        existentes = set(
            CatalogoCuenta.objects.values_list(
                "codigo_cuenta", flat=True
            )
        )

        nuevas = {}
        sin_codigo = 0

        for cuenta in ODT.objects.values_list(
            "cuenta_completa", flat=True
        ).iterator(chunk_size=2000):

            codigo = normalizar_codigo_cuenta(cuenta)

            if not codigo:
                sin_codigo += 1
                continue

            if codigo in existentes or codigo in nuevas:
                continue

            nombre = str(cuenta or "").strip()

            if " - " in nombre:
                nombre = nombre.split(" - ", 1)[1].strip()

            nuevas[codigo] = CatalogoCuenta(
                codigo_cuenta=codigo,
                nombre_cuenta=nombre[:250],
                ceco="",
                tipo_cliente="SIN_CLASIFICAR",
                requiere_revision_ceco=True,
                observaciones=(
                    "Cuenta incorporada desde ODT SoftGuard. "
                    "Pendiente de verificar CECO y clasificación B2B/B2C."
                ),
            )

        self.stdout.write(
            f"Cuentas existentes: {len(existentes)}"
        )
        self.stdout.write(
            f"Cuentas nuevas detectadas: {len(nuevas)}"
        )
        self.stdout.write(
            f"ODT sin código reconocible: {sin_codigo}"
        )

        if options["simular"]:
            self.stdout.write(
                self.style.WARNING(
                    "SIMULACIÓN: no se guardaron cambios."
                )
            )
            return

        with transaction.atomic():
            CatalogoCuenta.objects.bulk_create(
                list(nuevas.values()),
                ignore_conflicts=True,
                batch_size=500,
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Catálogo completado. "
                "Las cuentas existentes no fueron modificadas."
            )
        )
