"""Opciones de navegación y destinos de regreso internos; no concede permisos."""
from urllib.parse import urlencode, urlsplit

from django.urls import Resolver404, resolve, reverse
from django.utils.http import url_has_allowed_host_and_scheme

from .acceso_coordinadores import es_coordinador_sstt


def datos_menu(request, contexto):
    usuario = request.user
    if not usuario.is_authenticated:
        return {}
    bandeja = usuario.has_perm("revisiones.ver_bandeja_sstt")
    coordinador = contexto.get("es_coordinador")
    if coordinador is None:
        coordinador = es_coordinador_sstt(usuario)
    opciones = []

    def agregar(nombre, texto, permitido, activos=()):
        if permitido:
            opciones.append({"nombre": nombre, "texto": texto, "url": reverse(nombre),
                             "activos": (nombre, *activos)})

    agregar("bandeja", "Gestión de pagos", bandeja, ("detalle",))
    agregar("calendario_servicios", "Calendario de visitas", bandeja or usuario.has_perm("revisiones.ver_calendario_sstt"))
    agregar("analisis_odt", "Análisis de ODT", bandeja and not coordinador and usuario.has_perm("revisiones.revisar_pago_sstt"))
    agregar("bandeja_creacion", "ODT por creación", bandeja and not coordinador)
    agregar("odt_modificadas", "Seguimiento de cambios", bandeja and not coordinador)
    agregar("mantenimientos_preventivos", "Mantenimientos preventivos", bandeja and not coordinador)
    agregar("estadisticas_correcciones", "Análisis por coordinador", bandeja and not coordinador)
    agregar("historial_facturacion", "Facturación", not coordinador and usuario.has_perm("revisiones.exportar_pagos_sstt"),
            ("facturacion_previsualizar", "detalle_facturacion", "historial_requisiciones"))
    agregar("contratistas:listado", "Administrar contratistas", not coordinador and usuario.has_perm("contratistas.gestionar_contratistas_sstt"),
            ("contratistas:nuevo", "contratistas:editar", "contratistas:equivalencias", "contratistas:vinculacion_softguard"))
    agregar("administrar_cuentas", "Administrar cuentas SSTT", not coordinador and usuario.has_perm("revisiones.administrar_cuentas_sstt"))
    actual = getattr(getattr(request, "resolver_match", None), "view_name", "")
    permitidas = {nombre for opcion in opciones for nombre in opcion["activos"]}
    for opcion in opciones:
        opcion["activa"] = actual in opcion["activos"]
    inicio = reverse("bandeja" if bandeja else "calendario_servicios")
    volver = inicio
    if actual.startswith("contratistas:") and actual != "contratistas:listado":
        volver = reverse("contratistas:listado")
    elif actual in ("detalle_facturacion", "historial_requisiciones"):
        factura = contexto.get("facturacion") or contexto.get("factura")
        volver = reverse("historial_facturacion")
        if factura:
            volver += "?" + urlencode({"periodo": factura.periodo_id})
    # Un enlace directo tiene un regreso predecible; una visita desde otra
    # pantalla conserva su querystring sin aceptar destinos externos o acciones.
    referente = getattr(request, "META", {}).get("HTTP_REFERER", "")
    if referente and url_has_allowed_host_and_scheme(referente, {request.get_host()}, require_https=request.is_secure()):
        partes = urlsplit(referente)
        try:
            anterior = resolve(partes.path).view_name
        except Resolver404:
            anterior = None
        if anterior in permitidas and partes.path != request.path:
            volver = partes.path + ("?" + partes.query if partes.query else "")
    return {"opciones": opciones, "volver": volver,
            "en_inicio": getattr(request, "path", "") == inicio and volver == inicio,
            "usuario_id": usuario.pk}
