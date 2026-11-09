"""Enriquecimiento de filas con datos ya cargados; nunca decide acceso a ODT."""
from ..dominio.cuentas import normalizar_codigo_cuenta, tipo_cliente_cuenta


def preparar_filas(filas, *, coordinadores_pagina, facturadas, catalogo, puede_procesar, puede_asignar):
    """Requiere relaciones revision y seguimiento_correccion precargadas."""
    for odt in filas:
        monto_efectivo = (odt.valor_pago_editado if odt.valor_pago_editado is not None
                          else odt.valor_pago_tecnico)
        odt.monto_cero = monto_efectivo == 0
        seguimiento = getattr(odt, "seguimiento_correccion", None)
        odt.estado_modificacion = (
            seguimiento.estado if seguimiento else
            ("PENDIENTE" if odt.servicio_editado is not None or odt.valor_pago_editado is not None else "")
        )
        odt.puede_procesar_modificacion = (
            odt.estado_modificacion == "PENDIENTE"
            and puede_procesar
        )
        odt.permite_asignar_coordinador = False
        info = coordinadores_pagina[odt.numero]
        odt.coordinador_nombre = info.get("nombre") or "Sin identificar"
        odt.coordinador_identificado = bool(info.get("identificado", False))
        odt.permite_asignar_coordinador = (
            info.get("disponible", True) and not odt.coordinador_identificado
            and puede_asignar
        )


    for odt in filas:

        odt.esta_facturada = (
            odt.pk in facturadas
        )

        estado_revision = (
            odt.revision.estado
            if hasattr(odt, "revision")
            else None
        )

        odt.esta_rechazada = (
            estado_revision == "RECHAZADA"
        )

        odt.esta_bloqueada = (
            odt.esta_facturada
            or odt.esta_rechazada
        )



    for odt in filas:
        codigo = normalizar_codigo_cuenta(odt.cuenta_completa)
        cuenta = catalogo.get(codigo)
        odt.codigo_cuenta_catalogo = codigo
        odt.ceco_catalogo = cuenta.ceco if cuenta else ""
        odt.tipo_cliente_catalogo = tipo_cliente_cuenta(odt.cuenta_completa, catalogo)
        odt.ceco_requiere_revision = (
            cuenta.requiere_revision_ceco if cuenta else False
        )
        odt.cuenta_en_catalogo = cuenta is not None


    return filas
