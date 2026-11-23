# Prueba local del resumen intermedio de la bandeja

La primera fila financiera y la última fila operativa se conservan. El bloque
intermedio muestra tipos B2B/B2C/Sin clasificar, detalle de Cruz Verde y Tattersall, desglose por todos los servicios y cierres aprobados.

Todos los datos parten del mismo queryset autorizado y filtrado de la tabla,
antes de paginar. Se conserva el monto efectivo: editado si no es nulo, incluso
0 o la marca 2; en otro caso el original. Los resúmenes por cliente y servicio
incluyen rechazados para conciliar con el total efectivo. La primera tarjeta
superior sigue mostrando el original SoftGuard.

Las cuentas destacadas son un detalle adicional, no se suman otra vez. Se
identifican por nombre de cuenta (Cruz Verde/Cruzverde, Tattersall), sin
cambiar tipo de cliente ni CECO. Este criterio puede requerir un catálogo
explícito futuro si las denominaciones no incluyen la marca.

Mantenimiento aprobado incluye correctivas con/sin cobro, preventivos,
renovaciones, acuerdo comercial y presupuesto. Instalaciones B2C aprobadas
incluye solo el servicio genérico de nueva instalación B2C, excluye Cruzverde.
Otras ODT aprobadas se indican por separado para evitar omitirlas. Aprobado no
significa pagado. La regla actual sin revisión/POR_REVISAR no cambia.

Se mantiene la vista especial de Yasna sin tarjetas intermedias y la vista de
coordinadores sin indicadores financieros. No hay migraciones ni cambios de
montos, facturas, permisos, sincronización o clasificación guardada.

## Solo en el PC Windows, no en la Raspberry

Guardar el trabajo local y revisar `git status` antes de cambiar de rama. Si hay
cambios pendientes, resolverlos antes; no usar reset ni restaurar la base.

```powershell
git fetch origin
git switch --track origin/mejora/resumen-cuentas-servicios
.\.venv\Scripts\Activate.ps1
python manage.py check
python manage.py runserver
```

Abrir http://127.0.0.1:8000/ y recargar con Ctrl+F5. Usar los mismos filtros del
piloto para revisar. Las ediciones en el PC solo se reflejan en la base que use
ese entorno; este cambio visual no requiere editar datos para probarlo.

Verificar: primera y última fila intactas, totales B2B/B2C/Sin clasificar y por
servicio iguales al monto efectivo; detalle de marcas no sumado dos veces;
rechazados solo excluidos en cierres aprobados; fechas, contratistas, servicios,
monto y coordinador siguen afectando el resumen; comprobar en pantalla estrecha.

Para volver a la vista anterior: detener runserver (Ctrl+C), ejecutar
`git switch main` y volver a iniciar. No integrar el PR ni actualizar la Raspberry
hasta revisar y aprobar la prueba local. No ejecutar collectstatic local si se
usa runserver con la configuración habitual de desarrollo.

## Segunda versión ejecutiva

Se compacta el centro: importes B2B/B2C en dos bloques, cuentas destacadas en
líneas y servicios activos con monto, cantidad y barra por proporción de ODT.
Los servicios sin actividad y los criterios pasan a secciones desplegables.
Los cierres aprobados permanecen al pie. No cambia ningún cálculo del resumen.

Para actualizar la rama de prueba ya abierta en el PC, detener runserver,
ejecutar `git pull --ff-only` y volver a iniciar con `python manage.py runserver`.
Recargar con Ctrl+F5. No usar reset ni descartar settings.py o db.sqlite3.
Si Git informa conflicto, detenerse y conservar los cambios locales.
