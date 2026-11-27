from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from contratistas.models import Contratista


class Command(BaseCommand):
    help = "Habilita administración de contratistas a un usuario existente sin cambiar sus otros accesos."

    def add_arguments(self, parser):
        parser.add_argument("--usuario", required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            usuario = get_user_model().objects.get(username=options["usuario"])
        except get_user_model().DoesNotExist:
            raise CommandError("Usuario no encontrado. No se modificaron permisos.") from None
        permiso, _ = Permission.objects.get_or_create(
            content_type=ContentType.objects.get_for_model(Contratista),
            codename="gestionar_contratistas_sstt",
            defaults={"name": "Administrar contratistas SSTT"},
        )
        usuario.user_permissions.add(permiso)
        self.stdout.write(self.style.SUCCESS("Administración de contratistas habilitada. Se conservaron los demás permisos y grupos."))
