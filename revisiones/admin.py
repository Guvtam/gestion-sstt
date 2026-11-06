from django.contrib import admin
from django import forms
from django.contrib.auth import get_user_model
from .models import VinculoCoordinador
from .coordinadores_softguard import COORDINADORES_SOFTGUARD
from .models import ODT, Revision, EventoRevision, CatalogoCuenta
from .models import EjecucionSincronizacion
from .models import EventoRequisicion


@admin.register(EventoRequisicion)
class EventoRequisicionAdmin(admin.ModelAdmin):
    list_display = ("fecha", "facturacion_identificador", "contratista", "numero_anterior", "numero_nuevo", "usuario_nombre")
    search_fields = ("contratista", "numero_anterior", "numero_nuevo", "usuario_nombre")
    readonly_fields = tuple(campo.name for campo in EventoRequisicion._meta.fields)
    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(EjecucionSincronizacion)
class EjecucionSincronizacionAdmin(admin.ModelAdmin):
    list_display = (
        "id", "iniciada_en", "estado", "duracion", "fecha_carga_origen",
        "consultadas", "creadas", "actualizadas", "sin_cambios", "omitidas",
    )
    list_filter = ("estado",)
    readonly_fields = tuple(campo.name for campo in EjecucionSincronizacion._meta.fields)
    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False



@admin.register(ODT)
class ODTAdmin(admin.ModelAdmin):
    list_display = ('numero','contratista','estado_softguard','monto_origen')
    search_fields = ('=numero','contratista')


@admin.register(Revision)
class RevisionAdmin(admin.ModelAdmin):
    list_display = ('odt','estado','actualizado_por','actualizado_en')
    list_filter = ('estado',)


@admin.register(EventoRevision)
class EventoAdmin(admin.ModelAdmin):
    list_display = ('odt','estado_anterior','estado_nuevo','usuario','fecha')
    readonly_fields = ('odt','estado_anterior','estado_nuevo','comentario','usuario','fecha')
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(CatalogoCuenta)
class CatalogoCuentaAdmin(admin.ModelAdmin):

    list_display = (
        "codigo_cuenta",
        "nombre_cuenta",
        "ceco",
        "tipo_cliente",
        "requiere_revision_ceco",
        "actualizado_en",
    )

    search_fields = (
        "codigo_cuenta",
        "nombre_cuenta",
        "ceco",
    )

    list_filter = (
        "tipo_cliente",
        "requiere_revision_ceco",
    )

    readonly_fields = (
        "creado_en",
        "actualizado_en",
        "actualizado_por",
    )

    def save_model(self, request, obj, form, change):
        obj.actualizado_por = request.user
        super().save_model(request, obj, form, change)




class VinculoCoordinadorForm(forms.ModelForm):
    usuario_softguard = forms.ChoiceField(
        label="Responsable SoftGuard",
        choices=[(d["usuario"], d["nombre"]) for d in COORDINADORES_SOFTGUARD.values()],
    )

    class Meta:
        model = VinculoCoordinador
        fields = ("usuario", "usuario_softguard", "activo")

    def clean(self):
        datos = super().clean()
        usuario = datos.get("usuario")
        responsable = datos.get("usuario_softguard")
        if usuario and (usuario.is_superuser or usuario.get_username().strip().casefold() in ("admin", "jiturriaga")):
            raise forms.ValidationError("Las cuentas de administración no pueden vincularse como coordinador.")
        if usuario and responsable and datos.get("activo"):
            # No dejar otra cuenta histórica activa con el mismo alcance.
            anterior = get_user_model().objects.filter(
                username__iexact=responsable, is_active=True).exclude(pk=usuario.pk)
            for cuenta in anterior:
                vinculo = VinculoCoordinador.objects.filter(usuario=cuenta).first()
                if vinculo is None or (vinculo.activo and vinculo.usuario_softguard == responsable):
                    raise forms.ValidationError(
                        "Desactiva el acceso de la cuenta anterior antes de vincular este responsable.")
        return datos


@admin.register(VinculoCoordinador)
class VinculoCoordinadorAdmin(admin.ModelAdmin):
    form = VinculoCoordinadorForm
    list_display = ("usuario", "usuario_softguard", "activo", "actualizado_en")
    list_filter = ("activo",)
    search_fields = ("usuario__username", "usuario_softguard")
    readonly_fields = ("actualizado_en",)
    list_select_related = ("usuario",)
    actions = None

    def has_delete_permission(self, request, obj=None):
        # Desactivar conserva la restricción del perfil y evita el fallback histórico.
        return False
