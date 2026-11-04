"""Importa el CSV de equivalencias SSTT sin modificar cuentas existentes.
Uso:
 python manage.py importar_catalogo_cuentas catalogo_inicial_sstt.csv --simular
 python manage.py importar_catalogo_cuentas catalogo_inicial_sstt.csv
"""
import csv
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from revisiones.models import CatalogoCuenta


class Command(BaseCommand):
    help = 'Importa catálogo inicial de CECO y B2B desde CSV; preserva ediciones existentes.'

    def add_arguments(self, parser):
        parser.add_argument('archivo', help='Ruta al CSV UTF-8')
        parser.add_argument('--simular', action='store_true', help='Validar sin guardar')

    def handle(self, *args, **options):
        ruta = Path(options['archivo'])
        if not ruta.is_file():
            raise CommandError(f'No existe el archivo: {ruta}')
        obligatorias = {'codigo_cuenta', 'nombre_cuenta', 'ceco', 'tipo_cliente', 'requiere_revision_ceco', 'observaciones'}
        filas = []
        codigos = set()
        with ruta.open('r', encoding='utf-8-sig', newline='') as archivo:
            lector = csv.DictReader(archivo)
            if not obligatorias.issubset(set(lector.fieldnames or [])):
                raise CommandError('Faltan columnas requeridas en el CSV.')
            for n, fila in enumerate(lector, start=2):
                codigo = (fila['codigo_cuenta'] or '').strip().upper()
                tipo = (fila['tipo_cliente'] or '').strip().upper()
                ceco = (fila['ceco'] or '').strip()
                revisar = (fila['requiere_revision_ceco'] or '').strip() in ('1', 'True', 'true')
                if not codigo or len(codigo) > 100 or codigo in codigos:
                    raise CommandError(f'Código vacío, duplicado o demasiado largo en línea {n}: {codigo}')
                if tipo not in ('B2B', 'B2C') or len(ceco) > 50:
                    raise CommandError(f'Tipo o CECO inválido en línea {n}')
                if revisar and ceco:
                    raise CommandError(f'CECO conflictivo no debe estar asignado en línea {n}')
                codigos.add(codigo)
                filas.append(CatalogoCuenta(
                    codigo_cuenta=codigo,
                    nombre_cuenta=(fila['nombre_cuenta'] or '').strip()[:250],
                    ceco=ceco,
                    tipo_cliente=tipo,
                    requiere_revision_ceco=revisar,
                    observaciones=(fila['observaciones'] or '').strip(),
                ))
        existentes = set(CatalogoCuenta.objects.filter(
            codigo_cuenta__in=codigos
        ).values_list('codigo_cuenta', flat=True))
        nuevos = [fila for fila in filas if fila.codigo_cuenta not in existentes]
        conflictos = sum(fila.requiere_revision_ceco for fila in nuevos)
        self.stdout.write(f'CSV: {len(filas)} | Ya existentes (se conservan): {len(existentes)} | Nuevas: {len(nuevos)} | Nuevas con CECO en conflicto: {conflictos}')
        if options['simular']:
            self.stdout.write(self.style.WARNING('SIMULACIÓN: no se guardó ningún registro.'))
            return
        with transaction.atomic():
            CatalogoCuenta.objects.bulk_create(nuevos, ignore_conflicts=True, batch_size=500)
        self.stdout.write(self.style.SUCCESS('Importación finalizada. Las cuentas existentes no fueron modificadas.'))
