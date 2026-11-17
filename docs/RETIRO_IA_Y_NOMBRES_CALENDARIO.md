# Retiro del piloto IA y nombres del calendario

Se retiran los módulos, rutas, controles, plantilla, pruebas específicas, configuración de ejemplo y guía del piloto IA. Se restauran los archivos de integración con Análisis de ODT y navegación a su contenido anterior al PR 81. Se conservan el Top 50, los siete servicios, la paginación, el retorno tras editar y todos los cambios anteriores.

El calendario de visitas daba prioridad a CatalogoCuenta.nombre_cuenta. La bandeja utiliza ODT.cuenta_completa, por lo que un catálogo antiguo podía mostrar otro cliente bajo el mismo código y número de ODT. El calendario ahora usa el texto de la misma ODT sincronizada; sus filtros, estados, fechas, permisos y enlaces se mantienen. Si no tiene texto, muestra Sin cuenta. No se modifica ni borra el catálogo: CECO y clasificación siguen usando sus reglas existentes.

No hay migraciones ni reemplazo de datos. No hay que retroceder main, usar git reset --hard ni copiar bases de datos del PC al servidor.

## PC con el piloto instalado

1. Detener runserver con Ctrl+C.
2. Actualizar con git pull --ff-only después de fusionar el PR.
3. En la terminal PowerShell retirar las variables temporales:

```powershell
Remove-Item Env:SSTT_OPENAI_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:SSTT_OPENAI_MODEL -ErrorAction SilentlyContinue
Remove-Item Env:SSTT_IA_HABILITADA -ErrorAction SilentlyContinue
Remove-Item Env:SSTT_IA_LOCAL_SECRET_KEY -ErrorAction SilentlyContinue
Remove-Variable claveIA -ErrorAction SilentlyContinue
python manage.py check
python manage.py runserver
```

Si se definió DJANGO_SETTINGS_MODULE=config.settings_ia_local, retirarlo solo en esa terminal antes de iniciar el módulo habitual. Ya no iniciar con --settings=config.settings_ia_local. No borrar ni sobrescribir settings_prueba del servidor.

La configuración privada settings_ia_local.py, si se creó manualmente, permanece ignorada para no publicarla accidentalmente. No es importada por el sistema normal. Puede conservarse fuera del proyecto o retirarse manualmente si ya no se necesita. Las variables persistentes que se hayan configurado fuera de esa terminal deben eliminarse en su ubicación original. Si la clave API era exclusiva de esta prueba, revocarla en la cuenta del proveedor; retirar código no revoca credenciales ni cancela recargas del proveedor.

## Raspberry sin el piloto

No requiere configurar ni limpiar credenciales IA. Al actualizar, los archivos IA anteriores se añaden y retiran en el historial de Git pero no se activan por ello ni se ejecutan migraciones. La versión final no contiene la integración IA. Se aplica la corrección de nombres sin tocar revisiones, correcciones, facturaciones, usuarios o catálogo.

Usar el procedimiento habitual con config.settings_prueba, verificar el servicio y refrescar el navegador. La prueba del calendario debe comparar la misma ODT en ambas pantallas, incluyendo casos con nombre divergente en el catálogo. Esto asegura coherencia entre pantallas, no acredita que el nombre de origen de SoftGuard sea correcto si el propio origen está equivocado.
