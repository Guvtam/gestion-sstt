from django.core.management.base import BaseCommand
from contratistas.vinculacion import aplicar_exactas, propuestas_vinculacion

class Command(BaseCommand):
    help = "Vincula coincidencias exactas del catálogo actual; los demás casos quedan para revisión manual."

    def add_arguments(self, parser):
        parser.add_argument("--simular", action="store_true")

    def handle(self, *args, **options):
        if options["simular"]:
            cantidad = sum(p["automatico"] for p in propuestas_vinculacion())
            self.stdout.write(f"SIMULACIÓN: {cantidad} coincidencias exactas; no se guardaron cambios.")
        else:
            cantidad = aplicar_exactas()
            self.stdout.write(self.style.SUCCESS(f"Vinculadas automáticamente: {cantidad}"))
        pendientes = sum(not p["automatico"] for p in propuestas_vinculacion())
        self.stdout.write(f"Pendientes de revisión manual: {pendientes}")
