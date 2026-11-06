from django.conf import settings
from django.db import models

class ODT(models.Model):
    numero = models.PositiveIntegerField(unique=True)

    # Técnico y contratista
    codigo_tecnico = models.CharField(max_length=20, blank=True)
    tecnico = models.CharField(max_length=200, blank=True)
    contratista = models.CharField(max_length=150, blank=True)

    # Cuenta y ubicación
    cuenta_completa = models.TextField(blank=True)
    direccion = models.CharField(max_length=300, blank=True)
    provincia = models.CharField(max_length=150, blank=True)
    localidad = models.CharField(max_length=150, blank=True)

    # Servicio
    tipo_servicio = models.CharField(max_length=30, blank=True)
    servicio = models.CharField(max_length=150, blank=True)
    descripcion_servicio = models.TextField(blank=True)
    observaciones_insumos = models.TextField(blank=True)

    # Clasificación
    tipo_cliente = models.CharField(
        max_length=20,
        choices=[
            ('B2B', 'B2B'),
            ('B2C', 'B2C'),
            ('SIN_CLASIFICAR', 'Sin clasificar'),
        ],
        default="SIN_CLASIFICAR",
    )

    # Estados y fechas
    estado_softguard = models.CharField(max_length=50, blank=True)
    fecha_creacion = models.DateTimeField(null=True, blank=True)
    fecha_modificacion = models.DateTimeField(null=True, blank=True)
    fecha_visita = models.DateField(null=True, blank=True)
    fecha_finalizacion = models.DateTimeField(null=True, blank=True)
    fecha_pago = models.DateTimeField(null=True, blank=True)

    # Usuario creador
    usuario_creador = models.CharField(max_length=200, blank=True)
    correo_creador = models.EmailField(blank=True)

    # Montos
    monto_origen = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0
    )
    costo_mano_obra = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0
    )
    valor_pago_tecnico = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0
    )

    # Tiempo
    tiempo_trabajo_hrs = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    servicio_editado = models.CharField(
        max_length=150,
        null=True,
        blank=True
    )

    valor_pago_editado = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True
    )

    modificado_manualmente = models.BooleanField(
        default=False
    )
    
    ESTADOS_INFORME = [
        ("NO_ENVIADO", "No enviado"),
        ("ENVIADO", "Enviado"),
        ("NO_APLICA", "No aplica"),
    ]

    estado_informe = models.CharField(
        max_length=20,
        choices=ESTADOS_INFORME,
        default="NO_ENVIADO",
    )

    informe_actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="informes_odt_actualizados",
    )

    informe_actualizado_en = models.DateTimeField(
        null=True,
        blank=True,
    )


    def __str__(self):
        return f'ODT {self.numero}'

class Revision(models.Model):
    ESTADOS = [('POR_REVISAR','Por revisar'),('EN_REVISION','En revisión'),('OBSERVADA','Observada'),('APROBADA','Aprobada'),('RECHAZADA','Rechazada')]
    odt = models.OneToOneField(ODT, on_delete=models.PROTECT, related_name='revision')
    estado = models.CharField(max_length=20, choices=ESTADOS, default='POR_REVISAR')
    observacion = models.TextField(blank=True)
    actualizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    actualizado_en = models.DateTimeField(auto_now=True)

class EventoRevision(models.Model):
    odt = models.ForeignKey(ODT, on_delete=models.PROTECT, related_name='eventos_revision')
    estado_anterior = models.CharField(max_length=20, blank=True)
    estado_nuevo = models.CharField(max_length=20)
    comentario = models.TextField(blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    fecha = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-fecha']



class CatalogoCuenta(models.Model):

    TIPOS_CLIENTE = [
        ("B2B", "B2B"),
        ("B2C", "B2C"),
        ("SIN_CLASIFICAR", "Sin clasificar"),
    ]

    codigo_cuenta = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        verbose_name="Código de cuenta SoftGuard",
    )

    nombre_cuenta = models.CharField(
        max_length=250,
        blank=True,
        verbose_name="Nombre de cuenta",
    )

    ceco = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Centro de costo",
    )

    tipo_cliente = models.CharField(
        max_length=20,
        choices=TIPOS_CLIENTE,
        default="SIN_CLASIFICAR",
    )

    requiere_revision_ceco = models.BooleanField(
        default=False,
    )

    observaciones = models.TextField(
        blank=True,
    )

    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cuentas_sstt_actualizadas",
    )

    actualizado_en = models.DateTimeField(
        auto_now=True,
    )

    creado_en = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        verbose_name = "Cuenta SSTT"
        verbose_name_plural = "Cuentas SSTT"
        ordering = ["codigo_cuenta"]

    def __str__(self):
        return (
            f"{self.codigo_cuenta} - "
            f"{self.nombre_cuenta}"
        )


class CorreccionODT(models.Model):
    ESTADOS = [("PENDIENTE", "Pendiente"), ("EN_PROCESO", "En proceso"), ("ACTUALIZADA", "Actualizada")]
    odt = models.OneToOneField(ODT, on_delete=models.PROTECT, related_name="seguimiento_correccion")
    estado = models.CharField(max_length=20, choices=ESTADOS, default="PENDIENTE", db_index=True)
    servicio_objetivo = models.CharField(max_length=150, blank=True)
    monto_objetivo = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    corrige_servicio = models.BooleanField(default=False)
    corrige_monto = models.BooleanField(default=False)
    actualizada_en = models.DateTimeField(null=True, blank=True)
    actualizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="correcciones_odt_actualizadas")
    gestionado_en = models.DateTimeField(null=True, blank=True)

class EventoCorreccionODT(models.Model):
    odt = models.ForeignKey(ODT, on_delete=models.PROTECT, related_name="eventos_correccion")
    estado_anterior = models.CharField(max_length=20, blank=True)
    estado_nuevo = models.CharField(max_length=20)
    detalle = models.TextField(blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    fecha = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-fecha", "-pk"]


class AsignacionCoordinadorODT(models.Model):
    odt = models.OneToOneField(ODT, on_delete=models.PROTECT, related_name="asignacion_coordinador")
    usuario_coordinador = models.CharField(max_length=50)
    asignado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    asignado_en = models.DateTimeField(auto_now_add=True)


# Registrar estos modelos durante django.setup(), sin depender de importar vistas.
# Se conserva su módulo original, tablas y migraciones existentes.
from .facturacion_models import EventoRequisicion, FacturacionContratista, FacturacionODT, PeriodoFacturacion
from .sincronizacion_models import EjecucionSincronizacion

from .coordinadores_models import VinculoCoordinador
from .coordinadores_models import ResponsableSoftGuard
from .coordinadores_models import ProyeccionCoordinadorODT
