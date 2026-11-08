
from django.urls import path

from .vistas import bandeja, odt, operaciones_odt, cuentas, correcciones
from .analisis_odt import analisis_odt
from .mantenimientos_preventivos import mantenimientos_preventivos
from .calendario_servicios import calendario_servicios
from .estadisticas_correcciones import estadisticas_correcciones
from .exportar_pdf import exportar_aprobados_pdf
from .facturacion import previsualizar_facturacion, actualizar_requisicion
from .historial_facturacion import historial_facturacion
from .detalle_facturacion import detalle_facturacion
from .historial_facturacion import eliminar_periodo_facturacion
from .historial_requisiciones import historial_requisiciones


urlpatterns = [
    path("facturacion/<int:facturacion_id>/historial-requisicion/", historial_requisiciones, name="historial_requisiciones"),
    path("analisis-odt/", analisis_odt, name="analisis_odt"),
    path("calendario-servicios/", calendario_servicios, name="calendario_servicios"),
    path("odt-por-creacion/", bandeja.bandeja_creacion, name="bandeja_creacion"),
    path("mantenimientos-preventivos/", mantenimientos_preventivos, name="mantenimientos_preventivos"),
    path("asignar-coordinador/", operaciones_odt.asignar_coordinador, name="asignar_coordinador"),
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
        bandeja.bandeja,
        name="bandeja",
    ),
    path(
        "odt/<int:numero>/",
        odt.detalle,
        name="detalle",
    ),
    path(
        "acciones/",
        operaciones_odt.acciones,
        name="acciones",
    ),
    path(
        "guardar-fila/",
        operaciones_odt.guardar_fila,
        name="guardar_fila",
    ),
    path(
        "historial/<int:numero>/",
        odt.historial_odt,
        name="historial_odt",
    ),
    path(
        "actualizar-revision/",
        operaciones_odt.actualizar_revision,
        name="actualizar_revision",
    ),
    path(
        "actualizar-informe/",
        operaciones_odt.actualizar_informe,
        name="actualizar_informe",
    ),
    path(
        "cuentas/",
        cuentas.administrar_cuentas,
        name="administrar_cuentas",
    ),
    path(
        "cuentas/<int:cuenta_id>/guardar/",
        cuentas.guardar_cuenta,
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
        bandeja.contratistas_disponibles_ajax,
        name="contratistas_disponibles_ajax"
    ),
    path(
        "facturacion/periodo/<int:periodo_id>/eliminar/",
        eliminar_periodo_facturacion,
        name="eliminar_periodo_facturacion",
    ),
    path("odt-modificadas/estado-correccion/", 
         operaciones_odt.cambiar_estado_correccion, 
         name="cambiar_estado_correccion"
    ),
    path(
        "odt-modificadas/",
        correcciones.odt_modificadas,
        name="odt_modificadas"
    ),
    path(
    "odt-modificadas/estadisticas/",
    estadisticas_correcciones,
    name="estadisticas_correcciones",
),
        
]
