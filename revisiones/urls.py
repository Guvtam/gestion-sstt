
from django.urls import path

from . import views
from .mantenimientos_preventivos import mantenimientos_preventivos
from .calendario_servicios import calendario_servicios
from .estadisticas_correcciones import estadisticas_correcciones
from .exportar_pdf import exportar_aprobados_pdf
from .facturacion import previsualizar_facturacion, actualizar_requisicion
from .historial_facturacion import historial_facturacion
from .detalle_facturacion import detalle_facturacion
from .historial_facturacion import eliminar_periodo_facturacion


urlpatterns = [
    path("calendario-servicios/", calendario_servicios, name="calendario_servicios"),
    path("odt-por-creacion/", views.bandeja_creacion, name="bandeja_creacion"),
    path("mantenimientos-preventivos/", mantenimientos_preventivos, name="mantenimientos_preventivos"),
    path("asignar-coordinador/", views.asignar_coordinador, name="asignar_coordinador"),
    path(
        "exportar-aprobados-pdf/",
        exportar_aprobados_pdf,
        name="exportar_aprobados_pdf",
    ),
    path(
        "facturar-periodo/",
        previsualizar_facturacion,
        name="facturacion_previsualizar",
    ),
    path(
        "historial-facturacion/",
        historial_facturacion,
        name="historial_facturacion",
    ),
    path(
        "",
        views.bandeja,
        name="bandeja",
    ),
    path(
        "odt/<int:numero>/",
        views.detalle,
        name="detalle",
    ),
    path(
        "acciones/",
        views.acciones,
        name="acciones",
    ),
    path(
        "guardar-fila/",
        views.guardar_fila,
        name="guardar_fila",
    ),
    path(
        "historial/<int:numero>/",
        views.historial_odt,
        name="historial_odt",
    ),
    path(
        "actualizar-revision/",
        views.actualizar_revision,
        name="actualizar_revision",
    ),
    path(
        "actualizar-informe/",
        views.actualizar_informe,
        name="actualizar_informe",
    ),
    path(
        "cuentas/",
        views.administrar_cuentas,
        name="administrar_cuentas",
    ),
    path(
        "cuentas/<int:cuenta_id>/guardar/",
        views.guardar_cuenta,
        name="guardar_cuenta",
    ),
    path(
        "facturacion/<int:facturacion_id>/requisicion/",
        actualizar_requisicion,
        name="actualizar_requisicion",
    ),
    path(
        "facturacion/<int:facturacion_id>/odt/",
        detalle_facturacion,
        name="detalle_facturacion",
    ),
    path(
        "ajax/contratistas/",
        views.contratistas_disponibles_ajax,
        name="contratistas_disponibles_ajax"
    ),
    path(
        "facturacion/periodo/<int:periodo_id>/eliminar/",
        eliminar_periodo_facturacion,
        name="eliminar_periodo_facturacion",
    ),
    path("odt-modificadas/estado-correccion/", 
         views.cambiar_estado_correccion, 
         name="cambiar_estado_correccion"
    ),
    path(
        "odt-modificadas/",
        views.odt_modificadas,
        name="odt_modificadas"
    ),
    path(
    "odt-modificadas/estadisticas/",
    estadisticas_correcciones,
    name="estadisticas_correcciones",
),
        
]
