from django.core.management.base import BaseCommand
from django.utils import timezone

from revisiones.models import EjecucionSincronizacion


def fecha(valor):
    return timezone.localtime(valor).strftime("%d/%m/%Y %H:%M:%S") if valor else "Sin registro"


class Command(BaseCommand):
    help = "Muestra último intento y última sincronización completa, sin consultar SQL Server"

    def handle(self, *args, **options):
        ultimo = EjecucionSincronizacion.objects.first()
        if ultimo is None:
            self.stdout.write("No hay ejecuciones registradas con esta versión.")
            return
        completa = EjecucionSincronizacion.objects.filter(estado="COMPLETADA").first()
        self.stdout.write(
            f"Último intento: #{ultimo.pk} - {ultimo.get_estado_display()}\n"
            f"Inicio: {fecha(ultimo.iniciada_en)}\n"
            f"Fin: {fecha(ultimo.finalizada_en)}\n"
            f"Duración: {ultimo.duracion if ultimo.duracion is not None else 'En curso o pendiente de recuperación'}\n"
            f"Consultadas: {ultimo.consultadas} | Creadas: {ultimo.creadas} | "
            f"Actualizadas: {ultimo.actualizadas} | Sin cambios: {ultimo.sin_cambios} | Omitidas: {ultimo.omitidas}\n"
            f"Carga más reciente observada en el último intento: {fecha(ultimo.fecha_carga_origen)}\n"
            f"Última completa sin omisiones: {fecha(completa.finalizada_en) if completa else 'Sin registro'}\n"
            f"Carga más reciente observada en esa completa: {fecha(completa.fecha_carga_origen) if completa else 'Sin registro'}\n"
            f"Código de error: {ultimo.codigo_error or 'Ninguno'}"
        )
