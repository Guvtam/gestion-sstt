# Total de ODT por coordinador

En **Análisis por coordinador**, el nuevo apartado cuenta todas las ODT por
**fecha de creación**, incluidas las que no tienen correcciones y todos los estados
SoftGuard. Por defecto consulta desde el 1 de enero del año actual hasta hoy.
Las fechas son inclusivas en la zona horaria del sistema. Se pueden cambiar o
vaciar ambas para consultar todo el histórico; con fechas activas no se incluyen
ODT cuya fecha de creación falte. Un período inválido se informa y no amplía resultados.

El gráfico **Total de ODT por coordinador** reemplaza el panel derecho
**Tipos de corrección**. Se retira la tabla adicional de carga. El gráfico izquierdo
de correcciones, los indicadores, resumen y detalle originales se mantienen.
Cada barra muestra el total de ODT de un coordinador, incluyendo las no modificadas,
y su proporción respecto del total del período. Se ordena de mayor a menor, con
cantidad visible y desplazamiento vertical si hay muchos coordinadores. Las fechas se seleccionan en el bloque superior, junto a coordinador, tipo y estado,
con un único botón Aplicar filtros. No hay formularios dentro de los gráficos.

El coordinador se resuelve con el mismo mecanismo de bandeja: asignación manual,
proyección local vigente y consulta de origen en lotes de hasta 250 cuando hace falta.
Se utiliza el responsable actual, no el historial de coordinadores ni el número de
visitas/acciones realizadas. Las ODT verificadas sin responsable se agrupan en
**Sin coordinador identificado**. Una falla al verificar no se interpreta como ese
grupo ni se presenta un total parcial: se informa **Total no disponible**.

El período por **fecha de creación** y el coordinador afectan toda la pantalla:
indicadores, gráfico de correcciones, gráfico de total de ODT, resumen y detalle.
Los filtros de tipo y estado de corrección solo afectan las modificaciones, para
que la carga total siga incluyendo las ODT sin cambios. Se aplica un mismo rango
validado a ambas consultas. Las fechas inválidas no amplían ninguna consulta;
se informa el error y no se muestran resultados fuera del período. Las opciones de coordinador incluyen
los encontrados en la carga aunque no tengan ninguna corrección. Los formularios
y enlaces conservan las fechas al cambiar los filtros.

No modifica usuarios, permisos, ODT, correcciones, pagos ni facturas; tampoco
requiere migraciones. Mantiene el acceso de la página. Actualizar código, publicar
estáticos, copiarlos al directorio Nginx y reiniciar sstt-prueba después de integrar.
Las pruebas usan una base aislada y origen simulado; no consultan SQL Server real.
