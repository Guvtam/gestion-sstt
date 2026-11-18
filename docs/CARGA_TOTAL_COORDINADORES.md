# Total de ODT por coordinador

En **Análisis por coordinador**, el nuevo apartado cuenta todas las ODT por
**fecha de creación**, incluidas las que no tienen correcciones y todos los estados
SoftGuard. Por defecto consulta desde el 1 de enero del año actual hasta hoy.
Las fechas son inclusivas en la zona horaria del sistema. Se pueden cambiar o
vaciar ambas para consultar todo el histórico; con fechas activas no se incluyen
ODT cuya fecha de creación falte. Un período inválido se informa y no amplía resultados.

La tabla muestra coordinador, total de ODT, columnas de los estados realmente
presentes y ODT con correcciones. Tiene totales y barras horizontales superior e
inferior. Se ordena por mayor número de ODT. Cada ODT cuenta una vez; las que tienen
seguimiento de corrección o edición local de monto/servicio forman un subconjunto,
no una cantidad adicional. Una corrección de monto y servicio no cuenta dos veces.
Se incluyen correcciones actualizadas y ediciones antiguas sin seguimiento.

El coordinador se resuelve con el mismo mecanismo de bandeja: asignación manual,
proyección local vigente y consulta de origen en lotes de hasta 250 cuando hace falta.
Se utiliza el responsable actual, no el historial de coordinadores ni el número de
visitas/acciones realizadas. Las ODT verificadas sin responsable se agrupan en
**Sin coordinador identificado**. Una falla al verificar no se interpreta como ese
grupo ni se presenta un total parcial: se informa **Total no disponible**.

El filtro de coordinador afecta ambos análisis. Los filtros de tipo y estado de
corrección solo afectan el análisis original de modificaciones. Las fechas del
nuevo apartado solo afectan la carga total: no cambian las estadísticas, montos,
detalle ni paginación del análisis anterior. Las opciones de coordinador incluyen
los encontrados en la carga aunque no tengan ninguna corrección. Los formularios
y enlaces conservan las fechas al cambiar los filtros.

No modifica usuarios, permisos, ODT, correcciones, pagos ni facturas; tampoco
requiere migraciones. Mantiene el acceso de la página. Actualizar código, publicar
estáticos, copiarlos al directorio Nginx y reiniciar sstt-prueba después de integrar.
Las pruebas usan una base aislada y origen simulado; no consultan SQL Server real.
