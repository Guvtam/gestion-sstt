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
