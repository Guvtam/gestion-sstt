from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from revisiones.acceso_calendario import GRUPO_INTERNOS
from revisiones.models import ODT


class Command(BaseCommand):
    help = "Habilita consulta del calendario solo de ServicioStgo y ServicioViña."

    def add_arguments(self, parser):
        parser.add_argument("--usuario", required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            usuario = get_user_model().objects.get(username=options["usuario"])
        except get_user_model().DoesNotExist:
            raise CommandError("Usuario no encontrado. Créalo primero en Administración / Usuarios.") from None
        # Evitar afirmar acceso exclusivo a alguien que conserva otros roles.
        from revisiones.acceso_coordinadores import es_coordinador_sstt
        otros = usuario.get_all_permissions() - {"revisiones.ver_calendario_sstt"}
        if usuario.is_staff or usuario.is_superuser or es_coordinador_sstt(usuario) or otros:
            raise CommandError("El usuario tiene otros roles o permisos. Revísalos antes de habilitar este perfil de solo calendario. No se cambió su acceso.")
        ct = ContentType.objects.get_for_model(ODT)
        permiso, _ = Permission.objects.get_or_create(content_type=ct,
            codename="ver_calendario_sstt", defaults={"name": "Consultar calendario de visitas SSTT"})
        grupo, _ = Group.objects.get_or_create(name=GRUPO_INTERNOS)
        grupo.permissions.set([permiso])
        usuario.groups.add(grupo)
        self.stdout.write(self.style.SUCCESS(
            f"{usuario.get_username()}: calendario de ServicioStgo y ServicioViña habilitado (solo consulta)."))
