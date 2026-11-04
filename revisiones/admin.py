from django.contrib import admin
from .models import ODT, Revision, EventoRevision, CatalogoCuenta



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
