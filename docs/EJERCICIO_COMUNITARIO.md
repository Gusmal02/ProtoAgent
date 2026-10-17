# Tu primer ejercicio: revisor de una empresa ficticia

## Objetivo

Una tienda y una consultoría simuladas concilian importes positivos únicos por
cuenta. ProtoAgent construye una capacidad, la verifica, la conserva y trata
de resolver otro encargo con la misma interfaz usando esa experiencia.
Tú revisas la entrega final. No necesitas credenciales ni pagar un modelo.

## Preparación

Usa Python3.12 y un entorno virtual, como explica [USO.md](USO.md). Instala
la candidata con el extra motor (`pip install ".[motor]"` desde su código).
Si aún no tienes la carpeta del proyecto:

```console
git clone --branch codex/p1-p3-programming https://github.com/Gusmal02/ProtoAgent.git
cd ProtoAgent
python -m venv .venv
```

Activa el entorno: en Windows, `.venv\Scripts\activate`; en Linux/macOS,
`source .venv/bin/activate`. Después instala con `python -m pip install ".[motor]"`.
En Windows puedes usar `python`; en Linux suele ser `python3`.
Desde la carpeta del proyecto ejecuta:

```console
python -I tools/h45_campaign.py ./mi-ejercicio --support tests/p123_support.py
```

La carpeta debe ser nueva. El programa realiza las misiones secuencialmente,
sin red, y conserva contratos, evidencia y resultados. Consulta `result.json`:
debe indicar `passed`. Si aparece `failure.json`, conserva todo antes de
reportar el problema; no modifiques resultados para aparentar aprobación.

## Qué debes revisar

Abre `mi-ejercicio/community-delivery/review.json`: contiene el encargo,
hash del artefacto y revisiones QA/Security vigentes. En `files/solution.py`
está el código entregado. Lee también las trazas de `contextual/target/`.

1. ¿El informe agrupa cuentas, evita duplicados y descuenta devoluciones?
2. ¿Entradas vacías y valores cero coinciden con el contrato?
3. ¿Las revisiones corresponden al mismo hash que se entrega?
4. ¿El código evita archivos externos, red y dependencias adicionales?
5. ¿Puedes explicar por qué aceptarías o rechazarías esta solución?

Escribe tu razonamiento en una nota propia. Cuando termines, elige UNA opción:

```console
python -m protoagent_framework.community mi-ejercicio/community-delivery --decision approve --reviewer "Tu nombre"
```

Para rechazar, cambia `approve` por `reject`. La decisión se guarda en
`human-decision.json` y no puede sobrescribirse. Si cambias el código, la
aprobación se deniega: hace falta una nueva entrega y revisión.

## Qué significa esta aprobación

Es una revisión local de un ejercicio, no autenticación empresarial ni permiso
para desplegar. No inventamos tu aprobación: la entrega queda pendiente hasta
que decidas. El caso usa compilador confiable y datos sintéticos; no ejecutes
plugins o código descargado de desconocidos bajo este protocolo.

## Cómo contribuir

Comparte versión, sistema, contrato, resultado esperado/observado y un ejemplo
sintético mínimo. No subas claves, datos personales ni bases privadas. Consulta
[CONTRIBUTING.md](../CONTRIBUTING.md) y [SECURITY.md](../SECURITY.md).

Después de revisión humana real se podrá preparar operación sostenida:
carga útil, SLO, retención, recursos, respuesta a incidentes y aprobación de
despliegue. Este ejercicio no lanza servicios ni una campaña de ocho horas.
