# Incorporación automática de cuentas

La lectura de clasificación, la sincronización y el comando
completar_catalogo_cuentas comparten el valor predeterminado B2C.

- Cuenta con código válido y clasificación B2B/B2C explícita: conserva ese valor.
- Cuenta con código válido sin clasificación efectiva: B2C.
- Texto sin código reconocible: Sin clasificar; no se crea una cuenta ficticia.
- CECO desconocido: vacío y pendiente de revisión. B2C no determina un CECO.

El comando de completar catálogo incorpora únicamente códigos faltantes.
No cambia cuentas existentes, clasificaciones manuales, CECO ni ODT.
La simulación permite revisar cantidades antes de escribir.
Las variantes de un mismo código se incorporan una sola vez.

Los marcadores históricos guardados como SIN_CLASIFICAR no se reescriben en
esta entrega; la regla de lectura sigue tratándolos como B2C si el código es
válido. El comando actualizar_tipo_cliente_odts permite recalcular la proyección
de clasificación de las ODT y tiene su propia opción --simular. No cambia pagos
ni servicios corregidos.

No requiere migraciones ni modificación de la configuración del entorno.
La sincronización utiliza el mismo valor predeterminado sin cambiar sus
transacciones, bloqueo o tratamiento de las ediciones locales.
