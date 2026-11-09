"""Inventario local de acceso; no inicia sesiones ni cambia permisos."""
import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from revisiones.acceso_coordinadores import datos_coordinador, es_coordinador_sstt
from revisiones.models import VinculoCoordinador


class Command(BaseCommand):
    help = "Revisa usuarios, permisos SSTT y vínculos locales sin consultar SQL Server ni escribir datos."

    def add_arguments(self, parser):
        parser.add_argument("--usuario", help="Limita la revisión a un nombre de usuario exacto.")
        parser.add_argument("--json", action="store_true", dest="como_json", help="Salida estructurada para comparar instalaciones.")

    def handle(self, *args, **options):
        usuarios = get_user_model().objects.order_by("username").prefetch_related("groups")
        if options["usuario"]:
            usuarios = usuarios.filter(username=options["usuario"])
            if not usuarios.exists():
                raise CommandError("No existe el usuario indicado.")
        informes = []
        for usuario in usuarios:
            coordinador = es_coordinador_sstt(usuario)
            responsable = datos_coordinador(usuario) if coordinador else None
            vinculo = VinculoCoordinador.objects.filter(usuario=usuario).first()
            permisos = sorted(p for p in usuario.get_all_permissions()
                              if p.split(".", 1)[0] in {"revisiones", "contratistas"})
            avisos = []
            if not usuario.is_active:
                avisos.append("Usuario inactivo: no puede iniciar sesión.")
            if usuario.is_active and not usuario.has_perm("revisiones.ver_bandeja_sstt"):
                avisos.append("Sin permiso para abrir la bandeja.")
            if coordinador and responsable is None:
                avisos.append("Coordinador sin identidad activa: acceso operativo bloqueado.")
            if vinculo and not coordinador:
                avisos.append("Vínculo de coordinador sin restricción de perfil: revisar excepción de administrador o superusuario.")
            if coordinador and any(p in permisos for p in (
                "revisiones.editar_odt_sstt", "revisiones.revisar_pago_sstt",
                "revisiones.exportar_pagos_sstt", "revisiones.administrar_cuentas_sstt",
                "contratistas.gestionar_contratistas_sstt", "contratistas.ver_bancos_contratistas_sstt",
            )):
                avisos.append("Permisos adicionales asignados; el perfil coordinador sigue restringiendo páginas y operaciones.")
            informes.append({
                "usuario": usuario.get_username(), "activo": usuario.is_active,
                "staff": usuario.is_staff, "superusuario": usuario.is_superuser,
                "grupos": sorted(g.name for g in usuario.groups.all()),
                "perfil_coordinador": coordinador,
                "responsable_softguard": responsable["usuario"] if responsable else None,
                "vinculo": ({"usuario_softguard": vinculo.usuario_softguard, "activo": vinculo.activo}
                            if vinculo else None),
                "permisos_django": permisos, "avisos": avisos,
            })
        if options["como_json"]:
            self.stdout.write(json.dumps(informes, ensure_ascii=False, indent=2))
            return
        self.stdout.write("Diagnóstico local de usuarios. Solo lectura; sin consultas a SQL Server.")
        self.stdout.write("Los permisos Django no reemplazan las restricciones de coordinador ni verifican acceso a una ODT concreta.")
        for informe in informes:
            self.stdout.write(f"\nUsuario: {informe['usuario']} | Activo: {informe['activo']} | Staff: {informe['staff']} | Superusuario: {informe['superusuario']}")
            self.stdout.write("Grupos: " + (", ".join(informe["grupos"]) or "Ninguno"))
            self.stdout.write("Perfil coordinador: " + str(informe["perfil_coordinador"]) + " | Responsable: " + (informe["responsable_softguard"] or "Sin vínculo activo o no aplica"))
            if informe["vinculo"]:
                self.stdout.write(f"Vínculo explícito: {informe['vinculo']['usuario_softguard']} | Activo: {informe['vinculo']['activo']}")
            self.stdout.write("Permisos Django: " + (", ".join(informe["permisos_django"]) or "Ninguno"))
            for aviso in informe["avisos"]:
                self.stdout.write("Revisar: " + aviso)
        self.stdout.write(f"\nUsuarios revisados: {len(informes)}. No se modificaron usuarios ni permisos.")
