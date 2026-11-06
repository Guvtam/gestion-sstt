# Componentes visuales compartidos

base_documento.html concentra el documento HTML, idioma, codificación,
viewport y bloques de título, estilos, atributos del body, cuerpo y scripts.

base_operativa.html hereda ese documento y comparte el encabezado SSTT.
Facturación, bandeja (pagos y creación), análisis, preventivos, calendario y
ODT modificadas reutilizan esa estructura. Cada pantalla conserva su título,
subtítulo y acciones de navegación.

Estadísticas por coordinador, administración de cuentas, detalle ODT y la base
de contratistas heredan el documento común y conservan sus encabezados propios.
Las cuatro pantallas de contratistas siguen heredando su base de sección.

Las páginas preventivas mantienen exclusivamente sus hojas propias: no reciben
bandeja.css, cuyos anchos mínimos alterarían su presentación.
Los atributos data-* de permisos y endpoints, el contenedor CSRF de bandeja,
formularios, identificadores y scripts se conservan.

La base no decide permisos ni agrega enlaces. Las vistas y los casos de uso
siguen controlando el acceso. Login conserva una estructura independiente.

## Alcance pendiente

Se comparte la estructura y el encabezado de las pantallas compatibles.
No se han unificado todos los filtros, tablas, mensajes ni estilos de sección.
Esa extracción requiere conservar sus distintos contratos de interacción.

## Validación

303 pruebas correctas, check y comprobación de migraciones sin incidencias.
Comparación del HTML renderizado anterior y nuevo en nueve plantillas con
contexto vacío de datos: misma estructura, estilos, enlaces y scripts,
normalizando solo espacios y variantes equivalentes de metadatos.
Las pruebas de aplicación cubren datos y permisos de los flujos existentes.

No se realizó revisión visual en navegador ni se accedió al servidor.
No requiere migraciones ni modificación de archivos estáticos.
