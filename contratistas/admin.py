from django.contrib import admin
from .models import Contratista, EquivalenciaSoftGuard

@admin.register(Contratista)
class ContratistaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "nombre_empresa", "rut", "ciudad", "activo")
    search_fields = ("nombre", "nombre_empresa", "rut", "nombre_softguard")
    exclude = ("numero_cuenta", "banco", "tipo_cuenta")


@admin.register(EquivalenciaSoftGuard)
class EquivalenciaSoftGuardAdmin(admin.ModelAdmin):
    list_display = ("nombre_softguard", "contratista")
    search_fields = ("nombre_softguard", "contratista__nombre")
    readonly_fields = ("clave_normalizada",)
