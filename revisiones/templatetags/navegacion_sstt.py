"""Enlaces de navegación que conservan filtros multivalor sin duplicar la página."""
from django import template
from django.http import QueryDict
from urllib.parse import urlunsplit

register = template.Library()


@register.simple_tag
def enlace_pagina(querystring, numero, parametro="page", ancla=""):
    if parametro not in ("page", "page_detalle"):
        raise ValueError("Parámetro de paginación no permitido.")
    numero = int(numero)
    if numero < 1:
        raise ValueError("La página debe ser positiva.")
    parametros = QueryDict(querystring or "", mutable=True)
    parametros[parametro] = str(numero)
    return urlunsplit(("", "", "", parametros.urlencode(), ancla or ""))


@register.simple_tag
def paginas_numeradas(pagina):
    """Todas las páginas de listados cortos; ventanas acotadas en listados grandes."""
    return list(pagina.paginator.get_elided_page_range(pagina.number, on_each_side=2, on_ends=1))
