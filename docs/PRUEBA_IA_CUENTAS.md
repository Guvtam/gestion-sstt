# Prueba de análisis de cuentas con IA

## Alcance

Piloto de consulta para superusuarios y miembros del grupo Supervisor con permisos de bandeja, revisión de pagos e historial. Los coordinadores, usuarios de calendario y otros perfiles no obtienen acceso por este cambio. No añade permisos, tablas ni migraciones; no modifica ODT, correcciones, pagos ni facturación.

En Análisis de ODT, debajo de cada cuenta del ranking aparece Analizar atenciones de esta cuenta. La nueva pantalla incluye todos los servicios de la cuenta, selecciona ODT Finalizadas por fecha de finalización y no hereda filtros adicionales del ranking. Para revisar el año, seleccionar 1 de enero hasta la fecha actual.

Primero se preparan antecedentes sin API externa. Se consulta el timeline en una sola consulta parametrizada, acotada a los números seleccionados. Un error SQL impide continuar: nunca se interpreta como historial vacío. Los eventos pueden tener fechas fuera del período de finalización. La cobertura distingue ODT, ODT con historial y eventos; ninguna cantidad afirma visitas físicas.

Límites del piloto: 100 ODT, 366 días de diferencia entre fechas, 5000 eventos, 3000 caracteres visibles por texto y 180000 bytes de antecedentes preparados. Si se excede un límite global se solicita reducir el período, no se analiza silenciosamente una muestra. Los textos recortados se identifican. Las solicitudes SQL y API tienen tiempos de espera y no se reintentan automáticamente. Esta versión es síncrona y no incorpora cola de trabajos, análisis masivo, caché persistente ni historial de análisis. No ejecutar varias cuentas simultáneamente en la Raspberry.

## Primera prueba en el PC sin API

1. Fusionar el PR revisado y actualizar el código en VS Code con git pull --ff-only, con el entorno virtual activo.
2. Iniciar el servidor local como habitualmente. No ejecutar fixtures ni reemplazar la base.
3. Ingresar como administrador. Abrir Análisis de ODT, elegir una cuenta y pulsar Analizar atenciones de esta cuenta.
4. Seleccionar el período y pulsar Preparar antecedentes sin enviar a IA. Esto requiere acceso a SQL Server; realizar la prueba desde la red de la oficina si no hay VPN.
5. Revisar cobertura, cantidades por servicio y el contenido preparado. Sin credencial también se puede probar este recorrido. No se muestra un análisis ficticio como si fuera IA.

## Habilitar una llamada real en el PC

Requiere una cuenta de API OpenAI con cuota y un modelo disponible que soporte Responses API y salidas estructuradas. Configurar un presupuesto en el proveedor. No se ha validado una llamada real desde este entorno: las pruebas de integración usan respuestas simuladas.

Antes de enviar información real, remediar la exposición de secretos/datos del repositorio y contar con autorización para tratar los antecedentes con el proveedor. La depuración automática de patrones NO garantiza anonimización: pueden persistir nombres o información sensible en texto libre. Revisar siempre la vista previa. Si contiene datos no autorizados, no enviar; esta pantalla no permite editar el origen. No conceder a la IA acceso directo a SQL, archivos o herramientas.

Con PowerShell en el proyecto y el entorno virtual activo:

```powershell
Copy-Item config/settings_ia_local.example.py config/settings_ia_local.py
$env:SSTT_IA_LOCAL_SECRET_KEY = python -c "import secrets; print(secrets.token_urlsafe(48))"
$env:SSTT_IA_HABILITADA = "1"
$env:SSTT_OPENAI_MODEL = Read-Host "Modelo habilitado en tu cuenta de API"
$claveIA = Read-Host "Clave de API OpenAI" -AsSecureString
$env:SSTT_OPENAI_API_KEY = [System.Net.NetworkCredential]::new("", $claveIA).Password
python manage.py runserver 127.0.0.1:8000 --insecure --settings=config.settings_ia_local
```

`--insecure` se usa únicamente para servir CSS y JS de esta prueba local con DEBUG=False. No usar este comando para publicar el sistema ni escuchar en 0.0.0.0. El módulo local usa la configuración y base del PC; verificar que no apuntan al piloto compartido. La clave local de sesión es temporal: habrá que iniciar sesión nuevamente.

El archivo settings_ia_local.py está ignorado por Git. Las credenciales se introducen sin imprimirlas y permanecen solo en ese proceso de PowerShell; no escribirlas en config/.env, código, PR, capturas ni chats. Cerrar la terminal o retirar las variables al terminar:

```powershell
Remove-Item Env:SSTT_OPENAI_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:SSTT_IA_HABILITADA -ErrorAction SilentlyContinue
Remove-Item Env:SSTT_OPENAI_MODEL -ErrorAction SilentlyContinue
Remove-Item Env:SSTT_IA_LOCAL_SECRET_KEY -ErrorAction SilentlyContinue
Remove-Variable claveIA -ErrorAction SilentlyContinue
```

No se inicia envío externo por el mero hecho de configurar las variables. Preparar y revisar los antecedentes; marcar la confirmación de autorización y pulsar Generar análisis con IA. El servidor vuelve a leer las fuentes: si cambiaron desde la revisión o transcurrieron 15 minutos, requiere nueva preparación. Una generación nueva puede consumir cuota. La aplicación no comprueba el presupuesto de la cuenta del proveedor.

El servidor exige envío habilitado, modelo y clave configurados, DEBUG=False y SECRET_KEY de al menos 40 caracteres. Esta comprobación de longitud no demuestra que una clave sea secreta; las credenciales y la clave de sesión deben ser privadas y no estar expuestas en Git. No copiar settings_test a producción.

## Datos y calidad de las conclusiones

No se incluyen nombre/dirección de cuenta, técnicos, usuarios ni montos como campos. Se extrae texto de observaciones y acciones, excluyendo imágenes y depurando patrones de enlaces, correos, teléfonos y firmas. La vista previa muestra exactamente los datos enviados; la identidad de cuenta queda en SSTT, pero números de ODT y textos podrían permitir identificación indirecta.

Se utiliza https://api.openai.com/v1/responses con salida JSON estructurada, herramientas desactivadas por ausencia de tools, store=false y máximo 4000 tokens de salida. store=false no equivale a una garantía de retención cero: revisar controles y condiciones aplicables del proveedor. Los errores externos se muestran resumidos, sin cuerpo del error ni credencial.

Los hallazgos separan problema, solución, hipótesis, recomendación y limitación. Cada uno debe citar fuentes existentes de la selección. Se rechazan referencias desconocidas y respuestas incompletas, pero la existencia de la referencia NO demuestra que la interpretación sea correcta. El supervisor debe contrastar los textos. El historial se abre con el mismo modal del sistema.

No se conserva el resultado en la base ni se reutiliza automáticamente; al salir de la pantalla, preparar y generar nuevamente puede consumir otra llamada. Validar primero varias cuentas conocidas y comparar hechos, recomendaciones y evidencia. No automatizar pagos ni responsabilizar a personas a partir de las conclusiones.

## Raspberry

No desplegar la habilitación externa sin completar la prueba y la revisión de seguridad. La nueva página y la vista previa funcionan con la API deshabilitada. Para una habilitación posterior en Gunicorn se necesitan variables de entorno privadas, configuración efectiva segura, capacidad y timeouts revisados. El total de preparación SQL más generación puede superar 30 segundos: no asumir que el timeout por defecto de Gunicorn alcanza. Antes de ampliar el uso, pasar a trabajos en segundo plano y control de cuota/concurrencia compartido.

Referencias de implementación: https://developers.openai.com/api/docs/guides/structured-outputs y https://developers.openai.com/api/docs/guides/your-data.

## Síntesis ejecutiva del análisis

La salida comienza con Por qué se concentran las atenciones y contiene hasta ocho hallazgos agrupados. Se distingue demanda operativa (capacitación, enrolamientos, insumos) de fallas técnicas, trabajos ejecutados y pendientes por medios, acceso o documentación. Cada punto admite hasta cuatro referencias representativas y mil caracteres. El servidor rechaza hallazgos repetidos literalmente, exceso de extensión, ausencia de síntesis inicial o referencias inválidas.

Las pruebas de funcionamiento sin fallas no deben describirse como reparaciones. Compras, cotizaciones y recomendaciones no acreditan instalación o reparación. No se deben equiparar textos duplicados de Observación y Finalizado con dos trabajos ni corregir por semejanza los números de ODT referidos en comentarios. La fuente OBS corresponde a la observación actual y usa la fecha de finalización como referencia; no representa una fecha de creación del comentario.

La síntesis aparece antes de la vista previa extensa. Las evidencias continúan desplegables y usan el historial compartido. No se calculan porcentajes o cantidades de causas mediante IA: las referencias son representativas, no una clasificación cuantitativa exhaustiva de las ODT.

Estas reglas mejoran la instrucción y las validaciones de estructura, pero no garantizan que cada inferencia sea correcta. Comparar nuevas generaciones con fuentes conocidas. Los resultados anteriores no se transforman automáticamente: generar un nuevo análisis después de actualizar, lo que puede consumir cuota de API.
