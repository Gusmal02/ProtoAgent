# Puerta de operación sostenida

Estado: **preparación; no iniciada**. Primero completar el ejercicio y revisión
humana real. Este documento no activa un servicio ni autoriza ocho horas.

## Qué congelar antes de iniciar

- Commit, wheel/hash y sistema operativo realmente calificados.
- Encargos concretos, frecuencia y duración; distinguir ejercicios de producción.
- Contratos, corpus verificado, permisos y límites totales, sin ampliarlos al fallar.
- Responsable humano, forma de cancelar y procedimiento de reconciliación.
- SLO de resultado correcto, latencia y recuperación elegido a partir de medidas.
- Recursos de proceso y crecimiento de disco; no detener aplicaciones ajenas.
- Retención y exportación de evidencia. Sin borrado automático de negativos.

## Perfil inicial propuesto para la empresa ficticia

Un trabajador secuencial, datos sintéticos y capacidades del compilador confiable.
Encargos alternos tienda/consultoría y requisito incompatible explícito; este
último debe rechazarse, no forzarse a pasar. Recuperación siempre revalidada;
QA/Security por hash y aprobación humana antes de admitir código nuevo.
Sin puertos públicos, APIs pagadas, secretos, clientes ni plugins arbitrarios.

Registrar por encargo: ID/contrato/artefacto, decisiones del motor, fuente de
memoria, sondas/pruebas, generación/búsqueda, presupuesto, CPU, memoria privada,
working set, disco, latencia y resultado. Medir por separado arranque y servicio.
No dar por cumplido un SLO a partir de un único benchmark corto.

## Respuesta a incidentes

Ante hash alterado, permiso revocado, efecto fuera de alcance o prueba de
seguridad negativa: detener admisión/publicación propias, conservar evidencia y
avisar al responsable. Una llamada o efecto incierto no se reintenta a ciegas.
Tras reiniciar, reconciliar recibos e identidad antes de continuar; presupuestos
no se reinician. No editar una misión fallida para hacerla parecer aprobada.

## Criterio de cierre

Duración real cumplida, todos los encargos explicados (éxito/rechazo/fallo),
sin duplicados ni efectos indebidos, evidencia recuperable y recursos dentro
de lo congelado. Un negativo válido se reporta; no se oculta detrás del promedio.
Revisión del informe por una persona antes de promover operación comunitaria.

El handoff de `community.py` es local y no autentica usuarios. Antes de abrir un
servicio multiusuario se necesitan autenticación, aislamiento real de ejecución,
cuotas por usuario, protección de secretos y política de actualización/seguridad.
