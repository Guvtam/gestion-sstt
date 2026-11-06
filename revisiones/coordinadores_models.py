"""Vínculo entre el login local y una identidad responsable del origen."""
from django.conf import settings
from django.db import models


class VinculoCoordinador(models.Model):
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    usuario_softguard = models.CharField(max_length=150, unique=True)
    activo = models.BooleanField(default=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Vínculo de coordinador"
        verbose_name_plural = "Vínculos de coordinadores"

    def __str__(self):
        return f"{self.usuario} → {self.usuario_softguard}"


class ResponsableSoftGuard(models.Model):
    id_softguard = models.PositiveIntegerField(unique=True)
    nombre = models.CharField(max_length=150)
    usuario_softguard = models.SlugField(max_length=50, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Responsable SoftGuard"
        verbose_name_plural = "Responsables SoftGuard"

    def __str__(self):
        return self.nombre


class ProyeccionCoordinadorODT(models.Model):
    odt = models.OneToOneField("revisiones.ODT", on_delete=models.CASCADE,
                              related_name="responsable_local")
    resultado = models.JSONField()
    firma_catalogo = models.CharField(max_length=64)
    verificado_en = models.DateTimeField()

    class Meta:
        verbose_name = "Responsable local de ODT"
        verbose_name_plural = "Responsables locales de ODT"
