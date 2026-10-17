# Guía de uso desde cero

Esta guía es para quien nunca ha utilizado ProtoAgent. Primero ejecutaremos
ejemplos pequeños con datos ficticios. No necesitas una API key ni un LLM.
Sí necesitas Python y poder copiar comandos en una terminal.

## 1. Antes de empezar: cuatro palabras útiles

- **Biblioteca:** código que tu programa importa para no escribirlo todo desde cero.
- **Terminal:** ventana donde escribes comandos. En Windows puedes abrir PowerShell.
- **Entorno virtual:** carpeta con el Python y paquetes de este proyecto, separados
  de los de otros proyectos. No es una máquina virtual.
- **Workspace:** carpeta donde el ejemplo guarda su trabajo. Los archivos `.sqlite`
  son bases de datos locales; no son servidores que debas instalar.

ProtoAgent es una API de Python: se usa desde código. No trae una ventana de chat
ni un servidor web al que enviar texto libre.

## 2. Prepara Python 3.12

Instala Python **3.12** para tu sistema. En Windows, abre una terminal nueva y prueba:

```powershell
py -3.12 --version
```

Debe aparecer `Python 3.12.x`. En Linux/macOS el comando suele ser:

```console
python3.12 --version
```

La candidata no admite 3.11 ni 3.13. No desinstales tu otro Python: pueden coexistir.
La descarga de dependencias necesita Internet; las misiones de esta guía son locales.
El motor instala librerías numéricas que ocupan bastante más espacio que el SDK.
Empieza con la opción básica si sólo quieres ver memoria y colaboración.

## 3. Descarga el proyecto

Si tienes Git:

```console
git clone https://github.com/Gusmal02/ProtoAgent.git
cd ProtoAgent
```

Si no tienes Git: entra al repositorio en GitHub, pulsa **Code → Download ZIP**,
extrae el archivo y abre una terminal dentro de la carpeta extraída. Puede
llamarse `ProtoAgent-main`. Debes ver `pyproject.toml`, `examples` y `README.md`.
Puedes comprobarlo con `dir` en PowerShell o `ls` en Linux/macOS.

No copies los símbolos de la terminal, como `PS C:\...>` o `$`; sólo los comandos.

## 4. Crea un entorno e instala

### Windows / PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install .
```

Si PowerShell bloquea `Activate.ps1`, no hace falta cambiar la seguridad del
sistema. Usa el Python del entorno directamente:

```powershell
.\.venv\Scripts\python.exe -m pip install .
```

En todos los comandos siguientes puedes sustituir `python` por
`.\.venv\Scripts\python.exe` si no activaste el entorno.

### Linux / macOS

```console
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install .
```

Si tu sistema no puede crear el entorno, instala el soporte `venv` de Python3.12
con el mecanismo de tu distribución. No uses `sudo pip install` como solución.
macOS no tiene una calificación de esta candidata; la instalación es orientativa.

### Comprueba la instalación

```console
python -c "import protoagent_framework as p; print(p.__version__)"
```

Resultado esperado: `0.1.0rc3`. Todavía no has iniciado ningún agente o servicio.
No se ofrece aquí una instalación desde PyPI: instalamos la copia descargada
con `pip install .` (el punto significa «esta carpeta»).

## 5. Primer ejemplo: guardar un informe sin duplicarlo

Este ejemplo usa sólo la instalación básica:

```console
python examples/referenced_data.py --workspace ./mi-primer-informe
```

Hace cuatro cosas: crea datos ficticios, guarda una referencia de memoria,
registra un informe y repite la misma operación para comprobar que no se duplica.
Al terminar debes ver un JSON que contiene:

```json
{"report": {"columns": ["id", "amount"], "row_count": 2}, "stored_once": true, "authority_from_memory": false}
```

El orden de las claves puede variar. `stored_once: true` indica que quedó un
informe, no dos. `authority_from_memory: false` recuerda que guardar información
no concede permisos para actuar. Este ejemplo es un recorrido de memoria y
efectos, no una decisión autónoma del motor.

La carpeta `mi-primer-informe` contiene los datos locales del ejemplo. Para
repetirlo usa otra carpeta, por ejemplo `./mi-segundo-informe`; no borres el
historial como método de recuperación.

## 6. Segundo ejemplo: una misión con motor

Instala el extra numérico en el MISMO entorno:

```console
python -m pip install ".[motor]"
python examples/local_counter.py --workspace ./mi-primer-agente
```

El objetivo es sencillo: llevar un contador a 2. ProtoAgent observa el valor,
elige acciones ofrecidas por el proveedor y comprueba si alcanzó el objetivo.
La sesión tiene un presupuesto máximo de 24 pasos.

Resultado correcto:

```json
{"status": "completed", "value": 2, "audit": true}
```

`completed` significa objetivo verificado; `value` es el contador y `audit`
comprueba el historial de la sesión. Que el proceso termine sin errores no basta
para declarar éxito: mira siempre el estado y el verificador del objetivo.

No cambies el presupuesto para hacer pasar un fallo desconocido. Conserva la
carpeta, la versión y el mensaje de error para diagnosticarlo.

## 7. Tu primer archivo Python

Crea `mi_agente.py` en la carpeta del repositorio con un editor de texto. No
guardes el archivo dentro de `.venv`. Copia lo siguiente:

```python
from pathlib import Path
from protoagent_framework import create_session
from protoagent_framework.durable_counter import DurableCounter

carpeta = Path("ejemplo-desde-codigo")
carpeta.mkdir(exist_ok=False)
proveedor = DurableCounter(carpeta / "recurso.sqlite", entity="demo", target=2)
sesion = None
try:
    sesion = create_session(
        carpeta / "sesion.sqlite", "mi-mision",
        budget=24, goal={"target": 2}, nodes=4,
    )
    sesion.start()
    resultado = sesion.run(proveedor, max_steps=24)
    print("Estado:", resultado["checkpoint"]["status"])
    print("Valor:", proveedor.value())
    print("Historial íntegro:", sesion.audit_intact())
finally:
    if sesion is not None:
        sesion.close()
    proveedor.close()
```

Ejecútalo:

```console
python mi_agente.py
```

Se espera `Estado: completed`, `Valor: 2` e `Historial íntegro: True`.
El archivo muestra los cinco elementos básicos:

1. Una carpeta propia para no mezclar misiones.
2. Un proveedor: traduce el contador al lenguaje del motor y ejecuta sus acciones.
3. Una sesión: guarda el avance y limita cuántos pasos puede consumir.
4. Un objetivo que el proveedor puede comprobar con datos reales del contador.
5. Un cierre en `finally`, incluso cuando ocurre un error.

El contador es una herramienta de ejemplo; no representa un sistema de pagos.

## 8. Colaboración entre responsables

```console
python examples/collaboration_data_ops.py --workspace ./mi-equipo
```

Data entrega un artefacto, un revisor aprueba su hash y Ops acepta la tarea
dependiente. Espera un objeto con `data`, `ops` y `deploy_performed: false`.
No se despliega nada. Este ejemplo programa la secuencia desde el host y usa
evidencia ficticia: ilustra el protocolo, no un especialista autónomo de QA.
En una aplicación real debes ejecutar el verificador antes de registrar «pass».

## 9. Cómo conectar tu propio trabajo

No empieces modificando el motor. Define primero:

1. **Objetivo comprobable:** por ejemplo, «el informe contiene estas columnas».
2. **Herramienta confiable:** función que hace el trabajo en un entorno autorizado.
3. **Observación:** estado numérico y contexto que verá el motor.
4. **Permisos y límites:** qué entidad puede cambiar y cuánto trabajo admite.
5. **Verificador:** función que comprueba el resultado, no una cadena «lo logré».

Usa `ToolDefinition` → `ToolRegistry` → `RegisteredProvider` para adaptar funciones.
`NativeToolStore` sirve cuando puedes registrar efecto y recibo en SQLite.
La [referencia API](API.md) detalla firmas y callbacks. Reutiliza
[referenced_data.py](../examples/referenced_data.py) para el patrón de transacción;
no ejecutes SQL o código recibido de usuarios como si fuera una herramienta segura.

El integrador escribe el adaptador y el verificador. ProtoAgent no inventa
automáticamente una herramienta competente para cualquier objetivo textual.

## 10. Pausar, continuar y terminar no son lo mismo

| Operación | Para qué sirve |
|---|---|
| `pause()` | Dejar una sesión no terminal detenida para continuarla. |
| `checkpoint()` | Consultar estado, usados, presupuesto y pendiente sin tablas privadas. |
| `close()` | Cerrar la conexión local; no reinicia el presupuesto ni borra la misión. |
| `Session.resume(ruta, id)` | Reabrir una sesión existente no terminal. Usa el proveedor y contrato compatibles. |
| `cancel()` | Marcar cancelación; no deshace mágicamente efectos externos ya enviados. |
| `complete(proveedor)` | Cerrar exitosamente sólo con objetivo verificado y sin operación pendiente. |

No crees otra sesión con el mismo identificador para «continuar». Tampoco intentes
reanudar una sesión `completed`, `cancelled` o `exhausted`: ya es terminal.
Una misión nueva requiere identidad propia. La recuperación de una operación
pendiente necesita revisar su recibo/estado nativo; no pulses «reintentar» a ciegas.

## 11. Errores frecuentes

| Mensaje o síntoma | Qué revisar |
|---|---|
| `python` / `py` no reconocido | Python instalado y terminal nueva; en Windows prueba `py -3.12`. |
| Python incompatible | Crea el entorno con3.12, no con otro ejecutable. |
| `ModuleNotFoundError` | Instala con el mismo Python que ejecutará el programa; revisa el entorno activo. |
| Falta `torch` o `numpy` | Instala `".[motor]"` en ese entorno. |
| `FileExistsError` | El ejemplo protege una carpeta existente; usa una carpeta nueva. |
| `session ID exists` | Para continuar usa `resume`, no `create_session` otra vez. |
| `session is terminal` | La misión terminó o se canceló; no es una sesión continuable. |
| `tool callbacks must be callable` | `payload` debe ser una función, por ejemplo `lambda vista: {}`, no `{}` directamente. |
| `tool definition` | Comprueba el `kind`: se admite `execute`, no `act`. Lista completa en API.md. |
| `PermissionError` / revisión obsoleta | Revisa autorización/contexto; no quites el control para aprobar. |
| `corrupt checkpoint` / presupuesto agotado | Conserva evidencias; no edites tablas ni reinicies el budget para ocultarlo. |

## 12. Seguridad y siguientes pasos

Trabaja con datos sintéticos. No guardes claves en código ni subas bases de
misiones a Issues. `-I` y los permisos del SDK no son una sandbox del sistema
operativo. Los backups/restauraciones requieren cooperación de los escritores.

`RuntimeConfig` permite vigilar espacio y entradas antes de admitir más trabajo;
no borra archivos ni impide por sí solo que una operación llene el disco.
Los límites y cierre de recursos son responsabilidad compartida con el host.

Después de ejecutar los ejemplos, lee [API.md](API.md) para construir tu adaptador,
[Technical.md](../Technical.md) para entender las pruebas y
[SECURITY.md](../SECURITY.md) antes de conectar recursos importantes.
Para salir del entorno virtual activado escribe `deactivate`. No queda un servidor
de ProtoAgent ejecutándose por haber importado la biblioteca.
