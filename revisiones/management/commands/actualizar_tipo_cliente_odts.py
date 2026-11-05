
from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction

from revisiones.models import ODT, CatalogoCuenta
from revisiones.cuentas_utils import normalizar_codigo_cuenta, tipo_cliente_cuenta


class Command(BaseCommand):
    help = (
        "Actualiza la clasificación de las ODT según el catálogo "
        "sin modificar pagos, revisiones ni otros campos."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--simular",
            action="store_true",
            help="Muestra los cambios sin guardarlos.",
        )

    def handle(self, *args, **options):

        simular = options["simular"]

        catalogo = {cuenta.codigo_cuenta: cuenta for cuenta in CatalogoCuenta.objects.all()}

        estadisticas = Counter()
        lote = []
        tamano_lote = 500

        def guardar_lote():
            if lote and not simular:
                with transaction.atomic():
                    ODT.objects.bulk_update(
                        lote,
                        ["tipo_cliente"],
                        batch_size=tamano_lote,
                    )
            lote.clear()

        odts = ODT.objects.only(
            "id",
            "cuenta_completa",
            "tipo_cliente",
        ).iterator(chunk_size=1000)

        for odt in odts:

            estadisticas["total"] += 1

            codigo = normalizar_codigo_cuenta(
                odt.cuenta_completa
            )

            if not codigo:
                estadisticas["sin_codigo"] += 1
            elif codigo not in catalogo:
                estadisticas["sin_catalogo"] += 1
            tipo_nuevo = tipo_cliente_cuenta(odt.cuenta_completa, catalogo)

            estadisticas[tipo_nuevo] += 1

            if odt.tipo_cliente != tipo_nuevo:
                odt.tipo_cliente = tipo_nuevo
                lote.append(odt)
                estadisticas["cambios"] += 1

            if len(lote) >= tamano_lote:
                guardar_lote()

        guardar_lote()

        self.stdout.write("")
        self.stdout.write(
            "=== CLASIFICACIÓN DE ODT SSTT ==="
        )

        self.stdout.write(
            f"ODT revisadas: {estadisticas['total']}"
        )

        self.stdout.write(
            f"Cambios de clasificación: {estadisticas['cambios']}"
        )

        self.stdout.write(
            f"B2B: {estadisticas['B2B']}"
        )

        self.stdout.write(
            f"B2C: {estadisticas['B2C']}"
        )

        self.stdout.write(
            f"Sin clasificar: {estadisticas['SIN_CLASIFICAR']}"
        )

        self.stdout.write(
            f"Sin código reconocible: {estadisticas['sin_codigo']}"
        )

        self.stdout.write(
            f"Sin cuenta en catálogo: {estadisticas['sin_catalogo']}"
        )

        if simular:
            self.stdout.write(
                self.style.WARNING(
                    "SIMULACIÓN: no se guardaron cambios."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "Clasificación de ODT actualizada correctamente."
                )
            )
