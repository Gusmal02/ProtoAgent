# Seguridad y fronteras de confianza

ProtoAgent0.1 es un SDK experimental para **Python del host y herramientas
locales confiables**, con archivos SQLite controlados. No lo expongas como
servicio público sin autenticación ni ejecutes plugins desconocidos en su proceso.
`python -I` aísla imports; **no es una sandbox del sistema operativo**.

## Qué debe proteger la aplicación

El integrador controla permisos de archivos/procesos, credenciales, verificador,
entidades, política vigente y transacciones nativas. No publiques grants del host
como herramientas invocables por actores no confiables. Información de memoria,
hashes, aprobaciones anteriores y respuestas de modelos no conceden autoridad.

Un hash identifica contenido, no demuestra que un informe falso sea verdadero.
Los callbacks de finalización son código confiable del host: no los rellenes con
afirmaciones textuales de un LLM. El efecto debe volver a comprobar autorización
y aprobación antes de comprometerse, incluso si existía una oferta de cierre.

## Garantías locales y límites

El gate incluye entidad, revisión, admisión, revocación, colisiones, fences,
presupuesto, serialización y backups. El efecto y su recibo pueden compartir
transacción en un proveedor local cooperativo. Esto no garantiza exactly-once
de una API remota sin idempotencia y consulta de estado. Un resultado incierto
permanece pendiente hasta reconciliarlo; no autoriza reenvío ciego.

La cadena de auditoría detecta cambios respecto de sus hashes. Un administrador
que puede reescribir el almacenamiento completo queda fuera de esa protección.
La versión no aporta cifrado ni auditoría externa inmutable. Un backup requiere
la cooperación de todos los escritores; restaurar no restaura permisos vigentes.

No se promete detección universal de vulnerabilidades, pentesting general,
protección contra ransomware ni rescate de cualquier sistema comprometido.

## Reportar un problema

No publiques claves, datos reales ni detalles explotables en una Issue pública.
Si el repositorio ofrece reporte privado de vulnerabilidades, úsalo. En caso
contrario, comunícalo al propietario por un canal privado previamente conocido.
Todavía no se designó una dirección privada de contacto; no uses una dirección
inventada ni abras un reporte público con secretos para suplir esa ausencia.

Incluye versión/commit, frontera afectada, reproducer sintético acotado y
resultado esperado frente al observado. La documentación no autoriza pruebas
en redes, cuentas o datos de terceros.

Antes de desplegar, revisa avisos actuales de dependencias y las medidas de tu
aplicación. El inventario y la revisión offline del paquete no equivalen a un
escaneo CVE actualizado ni a una auditoría independiente completa.
