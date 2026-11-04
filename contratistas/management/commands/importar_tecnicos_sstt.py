import re
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from contratistas.models import Contratista

class Command(BaseCommand):
    help = "Importa contratistas desde tecnicos.xlsx, hoja inicial; no modifica ODT ni pagos"

    def add_arguments(self, parser):
        parser.add_argument("archivo")
        parser.add_argument("--aplicar", action="store_true", help="Guardar cambios; sin este argumento solo simula")

    def handle(self, *args, **options):
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise CommandError("Instala openpyxl en el entorno Django: pip install openpyxl") from exc
        wb = load_workbook(options["archivo"], read_only=True, data_only=True)
        ws = wb.worksheets[0]
        rows = ws.iter_rows(values_only=True)
        headers = [str(v or "").strip().lower() for v in next(rows)]
        expected = ["nombre", "nombre_empresa", "rut", "fono", "correo", "ciudad", "banco", "tipo_cuenta", "numero_cuenta", "categoria"]
        if any(x not in headers for x in expected):
            raise CommandError("Columnas del Excel distintas a las esperadas")
        n_creados = n_actualizados = n_omitidos = 0
        with transaction.atomic():
            for row in rows:
                data = dict(zip(headers, row))
                nombre = str(data.get("nombre") or "").strip()
                rut = re.sub(r"[^0-9Kk]", "", str(data.get("rut") or "")).upper()
                if not nombre or not rut:
                    n_omitidos += 1
                    continue
                rut = rut[:-1] + "-" + rut[-1]
                defaults = {k: str(data.get(k) or "").strip() for k in expected if k not in ("nombre", "rut")}
                defaults["nombre"] = nombre
                if options["aplicar"]:
                    _, created = Contratista.objects.update_or_create(rut=rut, defaults=defaults)
                    n_creados += bool(created)
                    n_actualizados += not created
                else:
                    n_creados += 1
            if not options["aplicar"]:
                self.stdout.write("SIMULACIÓN: no se guardaron registros")
        self.stdout.write(f"Candidatos/creados: {n_creados}; actualizados: {n_actualizados}; omitidos: {n_omitidos}")
