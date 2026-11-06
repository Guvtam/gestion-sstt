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


def _sql_odts_completas(limite=None):
    limite = _validar_limite(limite)
    top = f'TOP ({limite})' if limite is not None else ''
    return f"""
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
    """


def iterar_odts_completas(limite=None, tamano_lote=250):
    """Lectura acotada en memoria; cerrar generador al abortar el consumo."""
    if not isinstance(tamano_lote, int) or not 1 <= tamano_lote <= 1000:
        raise ValueError("El tamaño del lote debe estar entre 1 y 1000.")
    sql = _sql_odts_completas(limite)
    conexion = obtener_conexion_sql()
    cursor = None
    try:
        cursor = conexion.cursor()
        cursor.execute(sql)
        columnas = [columna[0] for columna in cursor.description]
        while True:
            lote = cursor.fetchmany(tamano_lote)
            if not lote:
                break
            for fila in lote:
                yield dict(zip(columnas, fila))
    finally:
        try:
            if cursor is not None:
                cursor.close()
        finally:
            conexion.close()


def consultar_odts_completas(limite=None):
    """Compatibilidad para consumidores que necesitan una lista completa."""
    return list(iterar_odts_completas(limite=limite))


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


def consultar_eventos_coordinadores(numeros, usuarios):
    """Solo campos de atribución; las listas se parametrizan y se acotan."""
    from .dominio.validacion_odt import numero_odt
    numeros = list(dict.fromkeys(numero_odt(n) for n in numeros))
    usuarios = list(dict.fromkeys(int(u) for u in usuarios))
    if len(numeros) > 250 or len(usuarios) > 100:
        raise ValueError("El lote de responsables supera el límite permitido.")
    if not numeros or not usuarios:
        return []
    odts_sql = ",".join("?" for _ in numeros)
    usuarios_sql = ",".join("?" for _ in usuarios)
    return _consultar(f"""
        SELECT NumeroODT, FechaHora, Accion, IDUsuario
        FROM [DW_Reporting].[proyectos].[ODT_Timeline]
        WHERE NumeroODT IN ({odts_sql})
          AND TRY_CONVERT(INT, IDUsuario) IN ({usuarios_sql})
        ORDER BY NumeroODT ASC, FechaHora ASC, Id ASC
    """, (*numeros, *usuarios))
