from django.db import models
from django.conf import settings

class Contratista(models.Model):
    nombre = models.CharField(max_length=180)
    nombre_empresa = models.CharField(max_length=220, blank=True)
    rut = models.CharField(max_length=24, unique=True, null=True, blank=True)
    fono = models.CharField(max_length=50, blank=True)
    correo = models.EmailField(blank=True)
    ciudad = models.CharField(max_length=100, blank=True)
    banco = models.CharField(max_length=120, blank=True)
    tipo_cuenta = models.CharField(max_length=100, blank=True)
    numero_cuenta = models.CharField(max_length=80, blank=True)
    categoria = models.CharField(max_length=100, blank=True)
    nombre_softguard = models.CharField(max_length=180, blank=True, help_text="Equivalencia validada manualmente")
    activo = models.BooleanField(default=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    actualizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["nombre", "pk"]
        permissions = [("gestionar_contratistas_sstt", "Administrar contratistas SSTT"), ("ver_bancos_contratistas_sstt", "Consultar datos bancarios SSTT")]

    def __str__(self):
        return self.nombre


class EquivalenciaSoftGuard(models.Model):
    contratista = models.ForeignKey(Contratista, related_name="equivalencias", on_delete=models.CASCADE)
    nombre_softguard = models.CharField(max_length=180)
    clave_normalizada = models.CharField(max_length=180, unique=True, editable=False)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre_softguard"]

    def save(self, *args, **kwargs):
        from .utils import normalizar_nombre
        self.clave_normalizada = normalizar_nombre(self.nombre_softguard)
        if not self.clave_normalizada:
            raise ValueError("El nombre SoftGuard no puede estar vacío")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.nombre_softguard} → {self.contratista.nombre}"
