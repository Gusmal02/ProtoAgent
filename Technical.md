# ProtoAgent: arquitectura y evidencia técnica

Dev10 incorpora composición adaptativa con DAGs históricos ligados a código
revisado: tres encargos nuevos de tres entradas,100/100 reserva cada uno, frente
a agotamiento frío con igual catálogo y presupuesto. La primitiva stable-sort
por clave se implementó explícitamente tras el negativo dev9; no fue descubierta
por el motor. Calificación instalada:30 pruebas y todas las aceptaciones previas.
Ver [composición verificada](docs/COMPOSICION_VERIFICADA.md).

Dev8 añade `CapabilityReuseGenerator` y revisión humana local por hash.
El descriptor público filtra interfaces; un callback del host revalida ejemplos
del contrato nuevo y el motor decide recuperar o generar. Toda recuperación
requiere revisiones nuevas. Ver [ejercicio comunitario](docs/EJERCICIO_COMUNITARIO.md).
Comparación controlada inicial:100/100 en los tres brazos; recuperación elimina
8.055 candidatos de búsqueda en ese encargo, pero añade comprobaciones y no
mejora el tiempo contextual. No es aprendizaje de un nuevo algoritmo.

La rama candidata incorpora programación composicional `0.2.0.dev7`:
consulta [implementación, resultados y reproducción P1–P3](docs/PROGRAMACION_P123.md).
Calificación local instalada: 24 pruebas unitarias y aceptación integrada
con corte/reanudación, reparación por QA y mantenimiento de proyecto.
El resto de este documento conserva la referencia histórica rc3.

Documento técnico de la candidata **0.1.0rc3**. Para instalar y ejecutar sin
conocer el proyecto, empieza por [USO.md](docs/USO.md). Este documento distingue
contratos implementados, observaciones experimentales y capacidades aún abiertas.

Para juegos, SOC, contención y exploración matemática de versiones anteriores,
consulta [Experimentos por dominio](docs/EXPERIMENTOS.md). Ese registro diferencia
prototipos/adaptadores históricos de la calificación del SDK rc3 descrita aquí.

## 1. Arquitectura de ejecución

ProtoAgent distribuye un SDK Python y una clausura de dependencias del motor
resonante bajo namespace propio. Su origen es la investigación de campos de
percepción y memoria resonante; la entrega del SDK se evalúa aquí como software,
sin convertir sus pruebas funcionales en demostraciones de ventaja cognitiva.

La aplicación anfitriona —el **host**, código confiable escrito por el
integrador— define objetivo, observaciones, herramientas, verificadores y permisos.
`Engine` selecciona acciones; `Session` conserva el estado de la misión y el
presupuesto. El proveedor adapta el dominio y ejecuta los efectos autorizados.

```text
Aplicación anfitriona: objetivo + herramientas + autoridad + verificador
                              |
                 Session <-> Engine
                    |
         Proveedor / RegisteredProvider
                    |
         Efecto nativo + recibo durable
```

Las decisiones del motor no crean credenciales. La verificación de objetivo
es independiente de la recompensa numérica y del texto de una respuesta.

### Componentes públicos

| Componente | Responsabilidad |
|---|---|
| `Session`, `create_session` | Lifecycle, checkpoint, operaciones pendientes, budget y auditoría. |
| `Engine` | Decisión local; requiere dependencias numéricas opcionales. |
| `ToolRegistry`, `RegisteredProvider` | Registro y adaptación de herramientas confiables. |
| `NativeToolStore` | Transacción SQLite local para efecto y recibo vinculados. |
| `MemoryStore`, `MemoryReference` | Referencias con integridad, entidad y revisión. |
| `VerifiedToolMemory` | Registro, recuperación, materialización y revalidación de módulos. |
| `TeamCoordinator`, `RoleSession` | Miembros, autoridad y sesiones con motor por actor. |
| `Collaboration` | Responsable, dependencias, entrega y revisión de artefactos. |
| `RuntimeWorkspace`, `RuntimeConfig` | Backup cooperativo y límites de admisión. |

`GovernedRuntime` es una interfaz de compatibilidad en proceso. No se le
atribuyen automáticamente las garantías durables de `Session/NativeToolStore`.

## 2. Persistencia y fronteras de confianza

Una operación tiene identidad y binding: herramienta, entidad, revisión y
payload. La sesión conserva la intención; un proveedor cooperativo registra
efecto y recibo en una misma transacción. Un replay de la misma identidad y
binding recupera su recibo. Una colisión no se acepta como una nueva acción.

La implementación de referencia usa SQLite, WAL y commits durables. Esto no
convierte una petición HTTP arbitraria en exactly-once: un efecto remoto incierto
requiere reconciliación o resolución explícita, sin reenvío ciego ni presupuesto
reiniciado. Los escritores de un backup deben participar en el protocolo de
workspace. Restaurar un clon no debe restaurar autoridad vigente.

El historial encadenado detecta alteraciones respecto de sus hashes; no es
almacenamiento inmutable frente al administrador capaz de reescribirlo todo.
No se proporcionan cifrado, aislamiento de procesos hostiles ni IAM de infraestructura.

## 3. Finalización verificable

Se encontró una regresión concreta: el generador produjo un candidato y QA y
security aprobaron el mismo hash, pero la misión no se publicó; el motor eligió
abstenerse al cerrar. Ese resultado negativo se conservó.

La corrección introduce una oferta de finalización del proveedor confiable,
ligada a entidad, revisión, objetivo, hash del artefacto y evidencias. La sesión
congela esa información junto al binding del request. Una política explícita
del motor puede preferir una acción terminal válida sin eliminar la abstención.
El ejecutor vuelve a validar aprobación y autoridad al comprometer el efecto.

Esto es una política de ingeniería explícita, **no una política aprendida**.
Un callback de finalización no es un permiso ni debe fabricarse a partir de
una respuesta generativa que simplemente afirme haber aprobado.

## 4. Matriz de evidencia de la candidata

Las siguientes cifras corresponden a calificación local de rc3 en Windows x64,
CPython 3.12.13. Los perfiles comparten controles; no deben sumarse como si
midieran problemas independientes.

| Evaluación | Resultado observado | Interpretación |
|---|---|---|
| Gate completo instalado | 18/18 pruebas; 27.75 s | Integración del paquete con motor. |
| Gate base instalado | 13/13 pruebas; 3.22 s | Perfil sin dependencias numéricas. |
| Gobernanza por perfil | 273/273 controles en 64 episodios | Invariantes del banco determinista. |
| Ejemplos públicos |3/3 completo;2/2 base | Recorridos iniciales ejecutables. |
| Integridad de instalación |68 módulos comparados con el wheel | Sin sustitución de fuentes instaladas. |
| Rebuild desde fuente externa |Contenido de miembros del wheel idéntico | No se exige mismo ZIP binario: timestamps pueden variar. |
| Consumidor ciego asistido |2 tareas;2/24 créditos; reapertura intermedia | Uso independiente de interfaces públicas en otro dominio. |
| Regresión multifichero | 543/543 controles; misión completed | Corrección del cierre y validez del caso funcional. |

La suite pública cubre lifecycle, aislamiento de entidad/revisión, revocación,
revisión falsa u obsoleta, presupuesto, colisiones, corrupción y backup, biblioteca
recuperada y ejecutada, coordinación y replay. Incluye cortes físicos antes de
efecto, después de commit y después de publicar pero antes del checkpoint del
líder. La recuperación de este último caso no republicó ni reinició el presupuesto.

Código reproducible en [tests/](tests/) y [tools/release_gate.py](tools/release_gate.py).
La regresión ampliada de543 controles pertenece al laboratorio histórico: su
arnés y bases no se distribuyen aquí como si fueran parte de la suite pública.
Por tanto, el gate de este repositorio no afirma volver a ejecutar esos543.

### Consumidor ciego asistido

Un subagente integró una cola local usando documentación, ejemplos y firmas
públicas, sin leer deliberadamente la implementación ni pruebas privadas.
No recibió una solución de dominio del host. Se comprobaron dos efectos,
reapertura no terminal con checksum/versión/presupuesto conservados, replay,
memoria contextual, auditoría y rechazo de una operación nueva tras revocación.

La primera candidata de documentación tuvo ambigüedades: `kind='act'` inválido,
payload no callable y ejemplo ausente del paquete entregado al evaluador.
Un intento de reabrir una sesión ya completada fue rechazado. Se preservaron
esos negativos y se aclaró la guía. Un traceback inicial mostró incidentalmente
una línea del SDK; por eso no se presenta como ceguera perfecta ni prueba humana.

### Caso multifichero y coste observado

El motor solicitó generación, delegó revisiones y terminó publicando: siete
despachos, 76 evaluaciones de búsqueda, tres módulos y 25 líneas emitidas.
Hubo 407 efectos nuevos en el banco funcional. Latencias por comando del proceso
QA: p50=2.883 ms, p95=3.388 ms y p99=4.063 ms; CPU 0.75 s y pared QA 2.241 s.
Working set 30.47 MB, privada 20.60 MB y pico 32.80 MB. Misión total 4.917 s.

Estas métricas pertenecen al proceso QA del caso local, no a todo el motor ni
a un servicio bajo concurrencia real. El generador combina búsqueda aritmética
acotada y un compilador de interfaces fijo escrito con Codex. Almacenamiento,
plantillas, evaluadores y la política de finalización son ingeniería del host;
no se atribuyen al motor como programación libre o descubrimiento autónomo.

## 5. Colaboración y memoria: interpretación

Un ACK no equivale a una aprobación. La revisión se refiere al hash exacto de
un artefacto; modificar contenido invalida esa revisión. Las dependencias
bloquean la aceptación prematura de trabajo posterior. El ejemplo Data/DevOps
demuestra el protocolo con secuencia del host, no planificación colectiva abierta.

`VerifiedToolMemory` recupera capacidades con contexto y evidencia. Su wrapper
actual usa una firma constante: no se usa este resultado para afirmar ventaja
semántica del grafo o transferencia general. La recomendación de biblioteca no
admite por sí sola un artefacto ni concede permisos para ejecutarlo.

## 6. Recursos y compatibilidad

El SDK base no carga Torch al importarse. El extra `[motor]` incorpora NumPy,
Torch y NetworkX. El contrato de instalación requiere Python>=3.12,<3.13.
Los gates registran las versiones efectivas: rangos compatibles no significan
que cada combinación futura esté probada.

`RuntimeConfig` tiene por defecto 100 pasos, 512 MiB de workspace, 16 MiB de
reserva y 10000 entradas. Es un watchdog cooperativo, no una cuota atómica del
sistema operativo. El host debe revisar espacio antes de admitir trabajo nuevo,
cerrar conexiones y no borrar evidencias automáticamente al alcanzar un límite.

La política de recursos propone inicio 2.5 GB y emergencia 2 GB, con histéresis.
Los ensayos de laboratorio usaron una excepción humana para ejecución secuencial
con menos RAM; no es una recomendación de capacidad para producción.

## 7. Reproducción y CI

Construye wheel/fuente, instala el wheel en otro entorno y ejecuta el gate con
ese Python. No añadas `core` ni carpetas privadas a `sys.path`.
Ver [CONTRIBUTING.md](CONTRIBUTING.md).

[GitHub Actions](https://github.com/Gusmal02/ProtoAgent/actions) ejecuta perfiles
base/completo en Windows/Ubuntu con Python3.12, instalación limpia, límites de
tiempo y conservación de reportes. El estado de cada commit vive en Actions;
las cifras locales anteriores no sustituyen el resultado de la matriz remota.
El commit inicial de fuentes es `e3d5ba5`.

La CI inicial de ese commit terminó con éxito en los cuatro perfiles:
Windows/base, Windows/completo, Ubuntu/base y Ubuntu/completo.
[Ejecución verificable](https://github.com/Gusmal02/ProtoAgent/actions/runs/38999338255).
Es calificación de esa revisión y esos runners, no de cualquier Linux/macOS.

## 8. Frontera de la versión

La evidencia respalda una infraestructura local de decisión, autoridad, memoria
y continuidad bajo contratos concretos. Quedan fuera: síntesis Python general,
ventaja universal de equipo o memoria, aprendizaje transferible demostrado,
operación continua calificada, plugins hostiles y seguridad universal.
No se inició una campaña de ocho horas como parte de esta entrega.

La revisión offline de artefactos no detectó patrones conocidos de claves ni
archivos privados en la entrega auditada. No sustituye revisión actualizada de
vulnerabilidades de dependencias ni auditoría de seguridad de una aplicación final.
