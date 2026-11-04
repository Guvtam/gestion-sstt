import pyodbc
from django.conf import settings


def obtener_conexion_sql():
    """Conexión de solo lectura al origen DW_Reporting."""
    cfg = settings.SQL_EXPLORACION
    return pyodbc.connect(
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={cfg['SERVER']},{cfg['PORT']};"
        f"DATABASE={cfg['DATABASE']};"
        f"UID={cfg['USER']};"
        f"PWD={cfg['PASSWORD']};"
        "Encrypt=yes;"
        "TrustServerCertificate=yes;",
        timeout=15,
    )


def _validar_limite(limite):
    if limite is None:
        return None
    limite = int(limite)
    if limite < 1:
        raise ValueError('El límite debe ser mayor que cero.')
    return limite


def _consultar(sql, parametros=()):
    conexion = obtener_conexion_sql()
    try:
        cursor = conexion.cursor()
        cursor.execute(sql, *parametros)
        columnas = [columna[0] for columna in cursor.description]
        return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]
    finally:
        conexion.close()


def consultar_odts_prueba(limite=None):
    limite = _validar_limite(limite)
    top = f'TOP ({limite})' if limite is not None else ''
    return _consultar(f"""
        SELECT {top}
            Numero,
            FechaCreacion,
            CAST(NULL AS VARCHAR(50)) AS CodigoTecnico,
            Tecnico,
            TipoServicio,
            Servicio,
            Estado,
            ValorPagoTecnico
        FROM [DW_Reporting].[proyectos].[ODT]
        WHERE NULLIF(LTRIM(RTRIM(Tecnico)), '') IS NOT NULL
        ORDER BY Numero DESC
    """)


def consultar_odts_completas(limite=None):
    limite = _validar_limite(limite)
    top = f'TOP ({limite})' if limite is not None else ''
    return _consultar(f"""
        SELECT {top}
            Numero,
            FechaCreacion,
            FechaModificacion,
            FechaVisita,
            FechaFinalizacion,
            CuentaCompleta,
            CAST(NULL AS VARCHAR(50)) AS CodigoTecnico,
            Tecnico,
            Direccion,
            ProvinciaEstado AS Provincia,
            Localidad,
            TipoServicio,
            Servicio,
            ObservacionesInsumos,
            Estado,
            CorreoCreador,
            ODTCreadaPor AS UsuarioCreador,
            Usuario,
            ODTCreadaPor,
            ProvinciaEstado,
            Valor,
            CostoManoObra,
            FechaPago,
            ValorPagoTecnico,
            TiempoTrabajoTotalHrs AS TiempoTrabajoHrs,
            TiempoTrabajoTotalHrs,
            FechaCarga
        FROM [DW_Reporting].[proyectos].[ODT]
        ORDER BY Numero DESC
    """)


def consultar_historial_odt(numero_odt):
    return _consultar("""
        SELECT
            NumeroODT,
            FechaHora,
            Accion,
            Observacion,
            IDUsuario,
            NombreUsuario,
            CorreoUsuario,
            CorreoEnObservacion AS CorreoObservacion
        FROM [DW_Reporting].[proyectos].[ODT_Timeline]
        WHERE NumeroODT = ?
        ORDER BY FechaHora ASC, Id ASC
    """, (int(numero_odt),))
