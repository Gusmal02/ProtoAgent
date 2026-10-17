# Tu primer ejercicio: revisor de una empresa ficticia

## Objetivo

Una tienda y una consultoría simuladas concilian importes positivos únicos por
cuenta. ProtoAgent construye una capacidad, la verifica, la conserva y trata
de resolver otro encargo con la misma interfaz usando esa experiencia.
Tú revisas la entrega final. No necesitas credenciales ni pagar un modelo.

## Reglas exactas del encargo

En este ejercicio, «cuenta» se representa con la columna `group` e «importe»
con `amount`. Las dos tablas son `sales` (ventas/honorarios) y `returns`
(devoluciones). No se trata de una política contable de producción.

1. Cada tabla se deduplica **por el par `(group, amount)`**, de forma independiente.
   Dos filas A/3 idénticas cuentan una vez; A/3 y A/2 cuentan ambas. Una fila de
   ventas y otra de devoluciones no se eliminan entre sí. Esta regla deliberada
   no equivale a identificar transacciones reales: dos pagos distintos del mismo
   importe requerirían otro contrato y un identificador de transacción.
2. Sólo cuentan importes estrictamente positivos. Ventas cero o negativas no
   crean cuentas de salida; devoluciones negativas se ignoran. Una devolución
   cero no cambia el total (el programa puede conservarla internamente).
3. Se suman por cuenta las ventas positivas únicas y se restan las devoluciones
   positivas únicas. Si falta devolución, se resta cero.
4. Sólo aparecen cuentas con al menos una venta positiva. Una cuenta presente
   únicamente en devoluciones no se añade. El saldo final sí puede ser cero
   o negativo; no se filtra por el signo después de restar.
5. Se devuelve una lista ordenada por `group`, con columnas `group` y `amount`.
   Dos tablas vacías producen `[]`.

Ejemplo para revisar a mano:

```json
{"sales":[{"group":"A","amount":3},{"group":"A","amount":3},{"group":"A","amount":2},{"group":"B","amount":0}],"returns":[{"group":"A","amount":1},{"group":"A","amount":1},{"group":"A","amount":-2},{"group":"C","amount":8}]}
```

Resultado: `[{"group":"A","amount":4}]`: ventas3+2 menos devolución1.
B no tiene venta positiva; C sólo tiene devolución.

El formato admitido es acotado: exactamente esas dos tablas; hasta100 filas por
tabla; cada fila contiene sólo esas dos columnas, cuenta de texto e importe
entero (no booleano), con valor absoluto hasta10000. No se admiten decimales.

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

### Reproducir el hash de la entrega

`artifact_hash` **no es el SHA256 de los bytes de solution.py**. Se calcula sobre
el diccionario completo `{nombre_archivo: texto}`. El texto se lee como UTF-8
normalizando saltos de línea; luego se serializa como JSON con claves ordenadas,
sin espacios entre campos y escapes ASCII (`ensure_ascii=True`). Finalmente se
aplica SHA256 a ese JSON codificado como UTF-8. Cambiar nombres o texto cambia
el hash; el orden de las claves del diccionario no lo cambia.

Desde la carpeta del proyecto puedes comprobarlo sin ejecutar el código entregado:

```console
python -c "import json,hashlib,pathlib; p=pathlib.Path('mi-ejercicio/community-delivery'); r=json.loads((p/'review.json').read_text(encoding='utf8')); f={n:(p/'files'/n).read_text(encoding='utf8') for n in r['files']}; h=hashlib.sha256(json.dumps(f,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('utf8')).hexdigest(); print('Calculado:',h); print('Registrado:',r['artifact_hash']); assert h==r['artifact_hash'], 'La entrega cambio: necesita nueva revision'"
```

Si tu carpeta tiene otro nombre, cambia `mi-ejercicio/community-delivery` en el
comando. El comando comprueba identidad del mapa de archivos declarado, no la
calidad del código ni la identidad de una persona. `contract_hash` usa la misma
serialización sobre el objeto `contract`; QA/Security deben referir el mismo
`artifact_hash`. El comando de aprobación comprueba además el manifest y las
revisiones: no sustituye leerlas ni concede permisos de despliegue.

1. ¿El informe agrupa cuentas, evita duplicados y descuenta devoluciones?
2. ¿Entradas vacías y valores cero coinciden con el contrato?
3. ¿Las revisiones corresponden al mismo hash que se entrega?
4. ¿El código evita archivos externos, red y dependencias adicionales?
5. ¿Puedes explicar por qué aceptarías o rechazarías esta solución?

Escribe tu razonamiento en una nota propia. Cuando termines, elige UNA opción:

```console
python -I -m protoagent_framework.community mi-ejercicio/community-delivery --decision approve --reviewer "Tu nombre"
```

Para rechazar, cambia `approve` por `reject`. La decisión se guarda en
`human-decision.json` y no puede sobrescribirse. Si cambias el código, la
aprobación se deniega: hace falta una nueva entrega y revisión.
`-I` utiliza la instalación del entorno, evitando importar por accidente otra
copia del SDK que tengas en la carpeta actual. Verifica primero el entorno activo.

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
La [puerta de operación sostenida](OPERACION_SOSTENIDA.md) enumera lo que
debe fijarse después de la revisión humana.
