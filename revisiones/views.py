"""Imports compatibles: las vistas HTTP residen en revisiones.vistas.

Los nuevos consumidores deben importar desde el módulo de responsabilidad.
Este archivo no contiene consultas, permisos ni lógica de negocio.
"""
from .consultas.pagos import (
    condicion_aprobada, error_odt_bloqueada, importe_efectivo,
    odt_facturada, odt_rechazada,
)
from .dominio.pagos import ESTADOS_APROBADOS, OPCIONES_BANDEJA
from .dominio.servicios import SERVICIOS_PRINCIPALES, nombres_canonicos
from .vistas.respuestas import (
    _respuesta_error_odt,
)
from .vistas.bandeja import (
    indicador,
    opciones_contratistas,
    bandeja,
    bandeja_creacion,
    contratistas_disponibles_ajax,
    SIN_TECNICO_FILTRO,
)
from .vistas.odt import (
    detalle, historial_odt,
)
from .vistas.operaciones_odt import (
    acciones,
    guardar_fila,
    actualizar_revision,
    actualizar_informe,
    cambiar_estado_correccion,
    asignar_coordinador,
)
from .vistas.cuentas import (
    administrar_cuentas, guardar_cuenta,
)
from .vistas.correcciones import (
    odt_modificadas,
)
