"""Trazabilidad de lectura del DW y persistencia local de ODT."""
from django.db import models
from django.utils import timezone


class EjecucionSincronizacion(models.Model):
    class Estado(models.TextChoices):
        EN_CURSO = "EN_CURSO", "En curso"
        COMPLETADA = "COMPLETADA", "Completada"
        CON_OMISIONES = "CON_OMISIONES", "Completada con omisiones"
        FALLIDA = "FALLIDA", "Fallida"
        INTERRUMPIDA = "INTERRUMPIDA", "Interrumpida"

    iniciada_en = models.DateTimeField(default=timezone.now, db_index=True)
    finalizada_en = models.DateTimeField(null=True, blank=True)
    duracion = models.DurationField(null=True, blank=True)
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.EN_CURSO, db_index=True)
    fecha_carga_origen = models.DateTimeField(null=True, blank=True)
    consultadas = models.PositiveIntegerField(default=0)
    creadas = models.PositiveIntegerField(default=0)
    actualizadas = models.PositiveIntegerField(default=0)
    sin_cambios = models.PositiveIntegerField(default=0)
    omitidas = models.PositiveIntegerField(default=0)
    cuentas_incorporadas = models.PositiveIntegerField(default=0)
    equivalencias_creadas = models.PositiveIntegerField(default=0)
    codigo_error = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ["-iniciada_en", "-pk"]
        verbose_name = "Ejecución de sincronización"
        verbose_name_plural = "Ejecuciones de sincronización"

    def __str__(self):
        return f"Sincronización {self.pk}: {self.get_estado_display()}"
