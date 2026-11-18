from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from revisiones.models import ODT


class Command(BaseCommand):
    help = 'Agrega acceso de pagos limitado a Mantenimiento nueva instalación; conserva grupos actuales.'

    def add_arguments(self, parser):
        parser.add_argument('--usuario', required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            usuario = get_user_model().objects.get(username=options['usuario'])
        except get_user_model().DoesNotExist:
            raise CommandError('Usuario no encontrado.') from None
        from .configurar_perfiles import PERMISOS_SSTT, PERMISOS_COORDINADOR
        codigos = [*PERMISOS_COORDINADOR, 'editar_odt_sstt', 'revisar_pago_sstt', 'exportar_pagos_sstt']
        ct = ContentType.objects.get_for_model(ODT)
        permisos = [Permission.objects.get_or_create(content_type=ct, codename=codigo,
                     defaults={'name': PERMISOS_SSTT[codigo]})[0] for codigo in codigos]
        permiso, _ = Permission.objects.get_or_create(content_type=ct,
            codename='gestionar_pagos_nueva_instalacion',
            defaults={'name': 'Gestionar pagos solo de Mantenimiento nueva instalación'})
        grupo, _ = Group.objects.get_or_create(name='Pagos nueva instalación')
        grupo.permissions.set([*permisos, permiso])
        usuario.groups.add(grupo)
        self.stdout.write(self.style.SUCCESS('Acceso adicional habilitado. Se conservaron los grupos y vínculos existentes.'))
