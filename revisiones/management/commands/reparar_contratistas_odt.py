"""Reparación local optativa, con simulación predeterminada y respaldo verificado."""
import os
from contextlib import closing
from pathlib import Path
import sqlite3
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from revisiones.casos_uso.contratistas_odt import reparar_lote_contratistas
from revisiones.integraciones.bloqueo_sync import bloquear_sincronizacion, SincronizacionEnCurso
from revisiones.models import ODT


def respaldar_sqlite(destino):
    if connection.vendor != 'sqlite':
        raise CommandError('El respaldo automático de este comando requiere SQLite.')
    ruta = Path(destino).expanduser().resolve()
    origen = Path(connection.settings_dict['NAME']).resolve()
    if ruta == origen:
        raise CommandError('El respaldo debe ser un archivo diferente de la base activa.')
    creado = False
    try:
        fd = os.open(ruta, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        creado = True
        connection.ensure_connection()
        with closing(sqlite3.connect(str(ruta))) as copia:
            connection.connection.backup(copia)
            if copia.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                raise ValueError('Respaldo inválido')
    except FileExistsError:
        raise CommandError('El archivo de respaldo ya existe. Usa un nombre nuevo; no se sobrescribe.') from None
    except Exception:
        if creado:
            ruta.unlink(missing_ok=True)
        raise CommandError('No se pudo crear y verificar el respaldo. No se inició la reparación.') from None
    return ruta


class Command(BaseCommand):
    help = 'Alinea contratista con técnico local de SoftGuard; simula por defecto, sin consultar SQL Server.'

    def add_arguments(self, parser):
        parser.add_argument('--aplicar', action='store_true')
        parser.add_argument('--respaldo', help='Archivo SQLite nuevo, obligatorio al aplicar.')

    def handle(self, *args, **options):
        aplicar = options['aplicar']
        if aplicar and not options['respaldo']:
            raise CommandError('Para aplicar debes indicar --respaldo con un archivo SQLite nuevo.')
        total = 0
        try:
            with bloquear_sincronizacion():
                if aplicar:
                    ruta = respaldar_sqlite(options['respaldo'])
                    self.stdout.write(f'Respaldo creado y verificado: {ruta}')
                ultimo = 0
                while True:
                    ids = list(ODT.objects.filter(pk__gt=ultimo).order_by('pk').values_list('pk', flat=True)[:250])
                    if not ids:
                        break
                    cambios = reparar_lote_contratistas(ids, aplicar=aplicar)
                    for numero, antes, nuevo in cambios:
                        if total < 20:
                            self.stdout.write(f'ODT {numero}: {antes or "Sin contratista"} -> {nuevo}')
                        total += 1
                    ultimo = ids[-1]
        except SincronizacionEnCurso as error:
            raise CommandError(str(error)) from None
        self.stdout.write(f'{"Actualizadas" if aplicar else "Diferencias detectadas (simulación)"}: {total}')
        self.stdout.write('Se conserva cada factura emitida. No se modifican montos, servicios, informes ni revisiones.')
