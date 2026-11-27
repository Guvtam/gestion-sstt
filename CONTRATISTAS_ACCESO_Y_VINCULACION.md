# Consulta de contratistas y vinculación

Toda persona con sesión iniciada puede abrir **Consultar contratistas → Ver datos** y consultar la ficha completa, incluidos banco, tipo y número de cuenta. La ficha es de lectura; crear, editar y vincular conservan el permiso `contratistas.gestionar_contratistas_sstt`. No hay acceso anónimo.

Los PDF autorizados de bandeja y facturación incluyen los datos bancarios del contratista vinculado, sin requerir el permiso bancario separado. Se mantienen el permiso de exportación, los filtros y las restricciones por perfil, incluido el servicio de nueva instalación. Si falta una vinculación válida, no se inventan datos.

## Filtro del catálogo

**Vinculación SoftGuard:** Todos, Pendientes por vincular y Vinculados. Un registro es pendiente si no tiene equivalencias ni un nombre SoftGuard manual validado del catálogo anterior. Un nombre formado solo por espacios no es vínculo. La búsqueda y el filtro se combinan y se conservan al cambiar de página. Consultar o filtrar nunca crea equivalencias ni cambia ODT.

## Raspberry: después de integrar el PR en main

Ejecutar desde el repositorio con el entorno virtual activo:

```bash
cd /home/tamara/gestion-sstt-prueba
source .venv/bin/activate
git status --short
```

Si aparecen cambios locales, revisar antes de actualizar; no descartar configuración ni bases de datos.

```bash
git pull --ff-only origin main
python manage.py check --settings=config.settings_prueba
python manage.py habilitar_administracion_contratistas --usuario jiturriaga --settings=config.settings_prueba
sudo systemctl restart sstt-prueba
sudo systemctl is-active sstt-prueba
```

Este cambio no requiere migraciones ni nuevos archivos estáticos. El comando agrega exclusivamente el permiso de administrar contratistas al usuario existente; es repetible y conserva grupos, contraseña y otros permisos. No lo convierte en staff ni superusuario. Si el usuario no existe, falla sin crear una cuenta.

Cerrar y abrir sesión con Juan Pablo y recargar con Ctrl+F5. Verificar: enlace Administrar contratistas, edición y vinculación; con otro usuario, consulta completa sin botones de edición. Probar PDF con un contratista vinculado y el filtro Pendientes por vincular.

La optimización de la exportación masiva queda pendiente. Por ahora se mantiene la descarga en grupos de cuatro contratistas.
