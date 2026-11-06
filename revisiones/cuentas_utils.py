"""Compatibilidad de imports y carga por lotes del catálogo de cuentas."""
from .dominio.cuentas import (normalizar_codigo_cuenta, normalizar_tipo_cliente, tipo_cliente_cuenta)


def cargar_catalogo_cuentas(cuentas):
    """Una regla de lectura para web, resúmenes, PDF y sincronización.

    CatalogoCuenta es la fuente de clasificación actual; ODT conserva una
    proyección para filtros SQL. Lotes acotados evitan límites de SQLite.
    """
    from .models import CatalogoCuenta
    codigos = sorted({codigo for texto in cuentas
                      if (codigo := normalizar_codigo_cuenta(texto))})
    catalogo = {}
    for inicio in range(0, len(codigos), 500):
        catalogo.update({
            cuenta.codigo_cuenta: cuenta
            for cuenta in CatalogoCuenta.objects.filter(codigo_cuenta__in=codigos[inicio:inicio+500])
        })
    return catalogo


