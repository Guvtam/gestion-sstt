from django.conf import settings
from django.db import models


class PeriodoFacturacion(models.Model):
    fecha_desde = models.DateField()
    fecha_hasta = models.DateField()
    creado_en = models.DateTimeField(auto_now_add=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['fecha_desde', 'fecha_hasta'], name='sstt_periodo_unico')]
        ordering = ['-fecha_hasta']

    def __str__(self):
        return f'{self.fecha_desde:%d/%m/%Y} - {self.fecha_hasta:%d/%m/%Y}'


class FacturacionContratista(models.Model):
    periodo = models.ForeignKey(PeriodoFacturacion, on_delete=models.PROTECT, related_name='facturaciones')
    contratista = models.CharField(max_length=150)
    numero_requisicion = models.CharField(max_length=100)
    creado_en = models.DateTimeField(auto_now_add=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['periodo', 'contratista'], name='sstt_periodo_contratista_unico')]
        ordering = ['contratista']

    def __str__(self):
        return f'{self.contratista} - {self.periodo}'


class FacturacionODT(models.Model):
    facturacion = models.ForeignKey(FacturacionContratista, on_delete=models.PROTECT, related_name='items')
    odt = models.OneToOneField('revisiones.ODT', on_delete=models.PROTECT, related_name='item_facturacion')
    servicio_facturado = models.CharField(max_length=150)
    monto_facturado = models.DecimalField(max_digits=14, decimal_places=2)
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'ODT {self.odt.numero} - {self.facturacion}'


class EventoRequisicion(models.Model):
    facturacion = models.ForeignKey(
        FacturacionContratista, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="eventos_requisicion",
    )
    facturacion_identificador = models.PositiveBigIntegerField(db_index=True)
    contratista = models.CharField(max_length=150)
    fecha_desde = models.DateField()
    fecha_hasta = models.DateField()
    numero_anterior = models.CharField(max_length=100, blank=True)
    numero_nuevo = models.CharField(max_length=100, blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    usuario_nombre = models.CharField(max_length=254)
    fecha = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-fecha", "-pk"]
        verbose_name = "Cambio de requisición"
        verbose_name_plural = "Cambios de requisición"

    def __str__(self):
        return f"Requisición de facturación {self.facturacion_identificador}"
