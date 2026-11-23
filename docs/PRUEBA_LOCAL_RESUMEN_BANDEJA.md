# Resumen ejecutivo por cuenta y servicio: prueba local

Se conservan la primera fila financiera y la última fila operativa de la bandeja.
El centro contiene una sola tabla: filas B2B, B2C, Cruz Verde y Tattersall;
columnas total ODT, monto total y cada servicio con monto y cantidad de ODT.
Si hay ODT sin clasificar se informa la fila correspondiente para no ocultarlas.
Servicios desconocidos también se muestran si existen. Las columnas sin actividad
muestran cero. La tabla tiene desplazamiento horizontal y primera columna fija.
No hay gráficos, bloque de mantenimiento aprobado/instalaciones ni criterios
plegables. Todos los resúmenes parten del queryset filtrado y autorizado, antes
de paginar. No se cambian pagos, permisos, facturación ni datos de las ODT.

Montos efectivos: editado si no es nulo, incluyendo 0 y la marca 2; en otro caso
original. Incluyen rechazados, como las tarjetas previas por servicio. La primera
tarjeta superior sigue mostrando el monto original SoftGuard.

Cruz Verde y Tattersall son detalle de B2B/B2C, nunca se suman otra vez. Se
identifican por nombre de cuenta (Cruz Verde/Cruzverde, Tattersall); no se cambia
tipo de cliente ni CECO. Puede requerirse catálogo explícito si el nombre no
incluye la marca. Enel no se muestra por separado, pero sus ODT siguen en su tipo.

La vista especial de Yasna mantiene solo sus tarjetas superiores y operativas;
coordinadores mantienen su vista sin resumen financiero. Sin migraciones.

## Actualizar solo en el PC, en la rama de prueba ya abierta

Detener runserver (Ctrl+C):

```powershell
git branch --show-current
git pull --ff-only
python manage.py check
python manage.py runserver
```

La rama debe ser `mejora/resumen-cuentas-servicios`. Abrir
http://127.0.0.1:8000/ y recargar Ctrl+F5. Si Git informa conflicto, detenerse;
no descartar settings.py ni db.sqlite3 ni usar reset. Se conservan los respaldos
y stash locales creados al iniciar la prueba.

Para una primera descarga, con trabajo local ya guardado:

```powershell
git fetch origin
git switch --track origin/mejora/resumen-cuentas-servicios
.\.venv\Scripts\Activate.ps1
python manage.py check
python manage.py runserver
```

Revisar que la suma de servicios de cada fila coincida con su total; B2B+B2C
(y sin clasificar si existe) concilie con el total efectivo. Cruz Verde y
Tattersall ya están incluidos. Verificar período y filtros idénticos a la tabla.
Para volver: detener servidor, `git switch main`, iniciar de nuevo; conservar
cambios locales. No integrar PR ni actualizar Raspberry hasta aprobar local.
