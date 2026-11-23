"""Alcance adicional de consulta; el grupo restringe y no amplía permisos."""
from django.db.models.functions import Lower, Trim

GRUPO_INTERNOS = "Calendario internos Santiago y Viña"
TECNICOS_INTERNOS = ("t. interno - serviciostgo", "t. interno - servicioviña")


def limitar_tecnicos_calendario(usuario, consulta):
    if not usuario.groups.filter(name=GRUPO_INTERNOS).exists():
        return consulta
    # Usar técnico actual, nunca el contratista histórico como alternativa.
    return consulta.annotate(_tecnico_calendario=Lower(Trim("tecnico"))).filter(
        _tecnico_calendario__in=TECNICOS_INTERNOS)
