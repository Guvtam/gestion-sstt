
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction

from revisiones.models import ODT


PERMISOS_SSTT = {
    "ver_calendario_sstt": "Consultar calendario de visitas SSTT",
    "ver_bandeja_sstt": "Ver bandeja de ODT SSTT",
    "ver_historial_sstt": "Consultar historial de ODT",
    "ver_montos_sstt": "Ver montos de pago",
    "cambiar_informe_sstt": "Cambiar estado del informe",
    "editar_odt_sstt": "Modificar servicio y monto de ODT",
    "revisar_pago_sstt": "Aprobar o rechazar pagos",
    "exportar_pagos_sstt": "Exportar PDF de pagos",
    "administrar_cuentas_sstt": "Administrar catálogo de cuentas",
}

PERMISOS_COORDINADOR = [
    "ver_calendario_sstt",
    "ver_bandeja_sstt",
    "ver_historial_sstt",
    "ver_montos_sstt",
    "cambiar_informe_sstt",
]

PERFILES_COMPLETOS = [
    "Supervisor",
    "Jefe",
    "Gerente",
]


class Command(BaseCommand):
    help = "Configura grupos y permisos del Sistema SSTT"

    @transaction.atomic
    def handle(self, *args, **options):

        content_type = ContentType.objects.get_for_model(ODT)

        permisos = {}

        for codigo, descripcion in PERMISOS_SSTT.items():
            permiso, _ = Permission.objects.get_or_create(
                codename=codigo,
                content_type=content_type,
                defaults={"name": descripcion},
            )
            permisos[codigo] = permiso

        coordinador, _ = Group.objects.get_or_create(
            name="Coordinador"
        )

        coordinador.permissions.set([
            permisos[codigo]
            for codigo in PERMISOS_COORDINADOR
        ])

        self.stdout.write(
            self.style.SUCCESS(
                "Perfil Coordinador configurado."
            )
        )

        for nombre in PERFILES_COMPLETOS:

            grupo, _ = Group.objects.get_or_create(
                name=nombre
            )

            grupo.permissions.set(list(permisos.values()))

            self.stdout.write(
                self.style.SUCCESS(
                    f"Perfil {nombre} configurado."
                )
            )

        calendario, _ = Group.objects.get_or_create(name="Calendario de visitas")
        calendario.permissions.set([permisos["ver_calendario_sstt"]])
        self.stdout.write(self.style.SUCCESS("Perfil Calendario de visitas configurado (solo consulta)."))

        self.stdout.write(
            self.style.SUCCESS(
                "Permisos SSTT configurados correctamente."
            )
        )
