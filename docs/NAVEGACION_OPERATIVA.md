# Navegación operativa compartida

El menú se muestra debajo del encabezado, antes del contenido, en las pantallas
de pagos, creación, análisis, seguimiento, calendario, preventivos, facturación,
cuentas y contratistas. Login y administración nativa de Django mantienen su layout.
El orden, estilos y opción activa se definen en un componente compartido.
Las acciones propias de una pantalla (guardar, facturar, buscar, crear contratista)
siguen junto a su contenido; los enlaces globales dejan de repetirse allí.

Las opciones respetan los permisos y la restricción de coordinador. El menú no
concede permisos: las vistas y casos de uso conservan su autorización existente.
Coordinadores ven Gestión de pagos y Calendario; el perfil Calendario solo ve
Calendario. Las cuentas sin acceso no reciben opciones operativas.

## Regreso

Volver ocupa el inicio de la misma franja en todas las pantallas. Por pestaña y
usuario, sessionStorage conserva los niveles de navegación con filtros múltiples
y página. Cambiar filtros dentro de una pantalla reemplaza ese nivel. Volver
retira el nivel actual, evitando ciclos y la repetición de formularios POST.
Sin almacenamiento JavaScript se usa un referente interno autorizado o el padre
de la pantalla: facturación con período, catálogo de contratistas o bandeja.
En el inicio sin pantalla anterior, el botón se presenta deshabilitado.
No se aceptan referentes externos, acciones de escritura ni administración Django.

## Tablas de análisis por coordinador

Resumen y detalle tienen overflow horizontal limitado al panel, foco de teclado
y una barra superior sincronizada con la inferior. La superior se oculta si todas
las columnas caben. ResizeObserver adapta el ancho al cambiar tamaño o contenido;
sin esa API se calcula al cargar y redimensionar. Sin JavaScript sigue disponible
la barra nativa inferior.

## Aplicación

No hay migraciones ni cambios de datos. En Raspberry ejecutar collectstatic con
config.settings_prueba y copiar al directorio que sirve Nginx:
/var/www/sstt-prueba/static/. Reiniciar sstt-prueba y recargar el navegador.
No incluye el cambio descartado de destacar correcciones Procesadas (PR 71).
