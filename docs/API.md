# Referencia pública de API — v0.1 experimental

API Python local, no HTTP/REST. Los identificadores del código están en inglés;
esta explicación está en español. Para empezar sin conocer las interfaces,
usa [USO.md](USO.md). No importes módulos privados del laboratorio.

## Sesiones

```python
from protoagent_framework import Session, create_session
```

`create_session(path, id, budget=..., goal=..., seed=..., nodes=...)` crea una
sesión nueva con motor. El directorio padre debe existir. `budget` limita pasos,
no memoria ni coste de una API externa. `goal` debe poder comprobarlo el proveedor.

- `start()`: comenzar; no terminal.
- `step(provider)`: una decisión/operación.
- `run(provider, max_steps=...)`: ejecución acotada, devuelve `checkpoint` y `results`.
- `pause()`, `cancel()`: pausa o cancelación de sesión; no rollback remoto.
- `checkpoint()`: mapping separado con `session_id`, `status`, `version`, `used`,
  `budget`, `checksum` y `pending`.
- `complete(provider)`: exige `provider.verify_goal(goal)` y ausencia de pendiente.
- `audit_intact()`: verifica integridad de cadena de historial, no inmutabilidad externa.
- `close()`: cerrar conexión, siempre en `finally`.
- `Session.resume(path, id, expected_version=...)`: existente no terminal;
  conserva usados/budget. No sustituir un contrato en ejecución por otro distinto.

Estados: `ready`, `running`, `paused`, `cancelled`, `completed`, `exhausted`.
Los últimos tres son terminales. No abrir tablas privadas para inspeccionar presupuesto.

## Herramientas y adaptación

```python
from protoagent_framework import (
    Observation, ToolDefinition, ToolRegistry, RegisteredProvider,
    ToolRequest, ToolResult, NativeToolStore,
)
```

`Observation(entity, revision, features, context=(0,0,0), state=None, description={})`
requiere tres o más características numéricas finitas y contexto de longitud3.
La revisión es entero no negativo. `state`/`description` deben ser serializables.

`ToolDefinition(name, kind, payload, handler=..., available=..., score=...,
control=..., artifact=..., agenda=..., completion=...)` registra código confiable.
Exactamente una de `handler` o `control`; no ambas. Los kinds válidos son
`observe`, `probe`, `execute`, `challenge`, `draft`, `compose`, `schedule`,
`cancel` y `delegate`.

| Callback | Firma y resultado |
|---|---|
| `payload` | `(vista: Observation) -> dict`; incluso un payload fijo necesita función. |
| `available` | `(vista) -> (bool, motivo: str)`. |
| `score` | `(vista) -> float` finito. |
| `handler` | `(operation_id: str, request: ToolRequest) -> ToolResult`. |
| `control` | `(request: ToolRequest) -> dict`; ruta de control de equipo registrada. |
| `completion` | `(vista) -> None` o prueba estructurada confiable de finalización. |

`ToolRegistry([definiciones...])` registra herramientas.
`RegisteredProvider(registry, observe, verify_goal, session=None)` conecta registro,
observador y verificador. Al reconstruir un proveedor con operación pendiente,
usa `session` para recuperar bindings congelados; no recalcules otra solicitud.

`ToolRequest(tool, entity, revision, payload, schema=1)` vincula el efecto.
`ToolResult(features, reward=0, terminal=False, evidence={})` devuelve observación
y evidencia; `terminal=True` no reemplaza el verificador del objetivo.

Proveedor de bajo nivel: `entity`, `observe()`, `legal_actions()`, `context_vector()`,
`state_key()`, `describe(observation)`, `request_binding(action)`,
`perform(operation_id, action)` y `verify_goal(goal)`. Sus bindings deben ser
estables para una operación pendiente. Es más sencillo comenzar con el registro
público que implementar todo este protocolo por primera vez.

## Transacciones de herramientas

`NativeToolStore(path, initialize=...)` abre almacenamiento local cooperativo.
`initialize(db)` prepara tablas de tu adaptador; se ejecuta al abrir, así que
para reapertura usa inicialización idempotente (`CREATE TABLE IF NOT EXISTS`).

`execute(id, request, mutate=..., authorize=...)` recibe:

- `mutate(db: sqlite3.Connection, request: ToolRequest) -> ToolResult`.
- `authorize(db, request) -> bool`: sólo `True` literal autoriza un efecto nuevo.

Efecto y recibo comparten transacción. Mismo id/binding devuelve recibo; conflicto
se rechaza. Obtener un recibo histórico no autoriza un efecto nuevo. Adaptadores
pueden imponer una política más estricta también al replay.
`read(sql, parameters=...)` es diagnóstico SELECT del host: no exponerlo a actores
no confiables. Ver ejemplo [referenced_data.py](../examples/referenced_data.py).

## Memoria, biblioteca y equipo

`MemoryStore.put(body, entity=..., revision=..., purpose=...) -> MemoryReference`;
`resolve(ref, entity=..., revision=...)` comprueba contexto e integridad.
Una referencia no es una credencial. Cierra el store al terminar.

`VerifiedToolMemory`, en `protoagent_framework.verified_tool_memory`, registra
módulos verificados del host, recupera candidatos, materializa archivos en una
carpeta propia y revalida para un contrato actual. No ejecuta código automáticamente
al materializar. `eligible` no equivale a admisión ni autoridad. La firma constante
del wrapper no prueba recuperación semántica general. Es una interfaz avanzada.

`TeamCoordinator` registra miembros y emite grants desde el host. `RoleSession`
da a cada actor una sesión/motor con su estado, no credenciales ocultas compartidas.
`Collaboration(team, path, reviewers=(...))`, en el submódulo `collaboration`,
separa `command(token, entity, id, action, task_id, payload)` e
`inspect(token, entity, task_id)`. La entrega y revisión se ligan al artefacto.
Ejemplo: [collaboration_data_ops.py](../examples/collaboration_data_ops.py).

## Finalización, errores y recursos

La prueba opcional `completion` contiene exactamente `entity`, `revision`,
`goal_scope`, `artifact_hash` y `evidence_hashes`; hashes SHA256 hexadecimales
minúsculos, lista no vacía. Host confiable la emite y el efecto revalida autoridad.
Una cadena «aceptado» no se transforma en prueba ni en permiso.

`ValueError`/`ReferenceError`: formato, contexto o integridad.
`PermissionError`/`TeamError`: autoridad o precondición del protocolo.
`SessionError`: sesión terminal, corrupta, versión incompatible o pendiente sin resolver.
`WorkspaceError`: backup/clon/lease. `WorkBudgetExceeded` y
`StorageBudgetExceeded`: no admitir trabajo nuevo; conservar evidencia.

`runtime_config.RuntimeConfig` controla vigilancia de pasos/espacio/entradas
desde el host, no ejecución forzosa del SO. `RuntimeWorkspace` exporta/restaura
clones cooperativos; los grants no deben revivir al restaurar. Un resultado
externo incierto no se trata como un error ordinario reintentable.

No captures cualquier excepción para seguir como si fuera éxito. No edites
presupuestos ni permisos en SQLite para hacer pasar una misión fallida.
