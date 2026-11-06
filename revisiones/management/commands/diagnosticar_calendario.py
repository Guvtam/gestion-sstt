"""Conciliación de cantidades; no imprime cuentas ni datos de conexión."""
from collections import Counter
from datetime import date
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count
from revisiones.consultas.calendario import visitas_del_mes, ESTADOS_VISITA
from revisiones.models import ODT, EjecucionSincronizacion
from revisiones.integraciones.transformacion_odt import transformar_registro, RegistroOrigenInvalido


class Command(BaseCommand):
    help = "Compara visitas locales y, opcionalmente, origen; solo lectura"

    def add_arguments(self, parser):
        parser.add_argument("--mes", required=True, help="AAAA-MM")
        parser.add_argument("--comparar-origen", action="store_true")

    def handle(self, *args, **options):
        try:
            mes = date.fromisoformat(options["mes"] + "-01")
            if not 1900 <= mes.year <= 9998:
                raise ValueError
        except ValueError:
            raise CommandError("Mes inválido. Usa AAAA-MM.") from None
        visitas = visitas_del_mes(mes)
        self.stdout.write(f"ODT locales totales: {ODT.objects.count()}\nVisitas locales del mes (sin filtros): {visitas.count()}")
        for estado, cantidad in visitas.order_by().values("estado_normalizado").annotate(n=Count("pk")).values_list("estado_normalizado", "n"):
            self.stdout.write(f"Estado {estado}: {cantidad}")
        for servicio, cantidad in visitas.order_by().values("servicio_efectivo").annotate(n=Count("pk")).values_list("servicio_efectivo", "n"):
            self.stdout.write(f"Servicio {servicio or 'Sin servicio'}: {cantidad}")
        ultimo = EjecucionSincronizacion.objects.first()
        self.stdout.write(f"Última sincronización: {ultimo.estado if ultimo else 'Sin registro'}; omitidas: {ultimo.omitidas if ultimo else 0}")
        if options["comparar_origen"]:
            from revisiones.servicios_sql import iterar_odts_completas
            cantidades = Counter()
            registros = iterar_odts_completas()
            try:
                for registro in registros:
                    cantidades["leidas"] += 1
                    try:
                        _, datos = transformar_registro(registro)
                    except RegistroOrigenInvalido:
                        cantidades["invalidas"] += 1
                        continue
                    visita = datos["fecha_visita"]
                    if (visita and visita.year == mes.year and visita.month == mes.month
                            and datos["estado_softguard"].strip().lower() in ESTADOS_VISITA):
                        cantidades["visitas"] += 1
                self.stdout.write(f"Origen: {cantidades['leidas']} ODT leídas; {cantidades['visitas']} visitas del mes; {cantidades['invalidas']} filas inválidas.")
            except Exception:
                raise CommandError("No se pudo comparar con el origen. No se modificaron datos locales.") from None
            finally:
                cerrar = getattr(registros, "close", None)
                if cerrar:
                    cerrar()
