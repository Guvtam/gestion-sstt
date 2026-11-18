# Acceso adicional: pagos de nueva instalación

El grupo **Pagos nueva instalación** agrega a una coordinadora la gestión de pagos
exclusiva del servicio **MANTENIMIENTO NUEVA INSTALACION**. No incluye
**MANTENIMIENTO NUEVA INSTALACION CRUZVERDE**. El permiso específico es
`revisiones.gestionar_pagos_nueva_instalacion`; no se comprueba ningún nombre de usuario.

## Activar tras integrar el cambio

En la Raspberry, actualizar código, publicar estáticos y ejecutar:

```bash
python manage.py habilitar_pagos_instalacion --usuario yramirez --settings=config.settings_prueba
sudo systemctl restart sstt-prueba
```

El comando crea el grupo/permisos si faltan y agrega el grupo, sin quitar
Coordinador, vínculos o permisos previos. Es idempotente. No convierte el usuario
en staff ni superusuario, no concede datos bancarios ni administración de cuentas.
No requiere migración. Para otro usuario, usar su nombre real con `--usuario`.
No se asigna acceso a nadie automáticamente durante el despliegue.

Cerrar sesión y volver a entrar. En el administrador también se puede asignar
el grupo creado; no asignar Supervisor para este fin. `configurar_perfiles` sigue
configurando los grupos anteriores sin eliminar este grupo adicional.

## Uso

- **Gestión de pagos** mantiene la bandeja propia de coordinadora: informes y
  Procesado de sus ODT, sin aprobación ni edición financiera de otros servicios.
- **Pagos nueva instalación** permite consultar todas las ODT del servicio,
  aunque su coordinador sea otro, filtrar, editar montos con confirmación,
  aprobar/rechazar, consultar historial y cambiar informe. No se permite cambiar
  el servicio para sacar una ODT de este alcance. Cruzverde queda excluido.
- **Facturar período** conserva el período 21–20, finalización, aprobación vigente,
  exclusión de ya facturadas, firma, bloqueo, unicidad e instantánea originales.
  El filtro por servicio se impone en servidor al previsualizar y confirmar;
  manipular la URL o enviar otros números no amplía el alcance.
- **Facturación** muestra un historial acotado con importes/servicios congelados,
  búsqueda, períodos, resumen de costos, contratistas, detalle y PDF solo de sus ODT autorizadas.
  Usa la misma plantilla y estilos del historial de supervisión.
- Una cabecera de contratista/período puede incluir otros servicios. En ese caso
  el número de requisición y su auditoría quedan a cargo de supervisión. Yasna
  puede consultar/exportar solo las ODT permitidas. Si la cabecera es exclusiva,
  puede actualizar su requisición y consultar su historial. No puede borrar
  períodos compartidos o completos desde este acceso.

Un usuario sin este permiso conserva las reglas anteriores. Juan Pablo y los
usuarios con acceso completo siguen gestionando y facturando los otros servicios
con la misma lógica. Si una ODT autorizada ya fue facturada, no se factura otra vez.
El servicio efectivo determina el alcance operativo; la instantánea facturada
lo determina en históricos, aunque después cambie el servicio actual de la ODT.

## Comprobación funcional

Entrar como coordinadora con ambos grupos. Verificar bandeja propia y nuevo acceso;
seleccionar el período; comparar con una sesión de supervisión; comprobar que
Cruzverde no aparece en la nueva pantalla, previsualización, historial ni PDF.
Solo después confirmar una facturación real. Pruebas automáticas usan base aislada
y origen simulado; no consultan SQL Server ni modifican datos del piloto.

En Pagos nueva instalación se muestran las cuatro tarjetas superiores de pagos y
las cuatro últimas de seguimiento; se omiten las tarjetas intermedias por servicio.
Los importes y conteos siempre se calculan sobre las ODT del alcance autorizado.
