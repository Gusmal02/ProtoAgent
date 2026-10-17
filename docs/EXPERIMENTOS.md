# ProtoAgent en distintos dominios: evidencia y contexto

Este registro resume documentación del laboratorio de investigación. No se
ejecutaron nuevas campañas para redactarlo. Los dominios corresponden a distintas
versiones, políticas, herramientas y adaptadores de la familia ProtoAgent.
El SDK rc3 no instala automáticamente esos laboratorios ni sus datasets.

## Juegos y navegación

### Laberintos 2D

El adaptador MazeAgent combinó señal de navegación del entorno, exploración y
memoria de bifurcaciones. En el ensayo5×5 alcanzó la meta en10 pasos; el random
walk de referencia promedió71. En8×8 alcanzó22 frente a176. Son resultados de
esos mapas, no una estimación estadística de ventaja en cualquier laberinto.
El segundo episodio5×5 volvió a10 pasos: no se atribuye mejora adicional a memoria.

Procedencia: `ideas/proto_agent.md`, sección «Resultados del laberinto»;
experimento histórico `diag_maze_agent.py`.

### Gymnasium / FrozenLake

G1 usó tres mapas deterministas y un sandbox de simulación reversible con
transiciones accesibles. Alcanzó12/12 metas y empató longitudes BFS6,6 y8.
Sandbox aquí significa simulación del estado del juego, no aislamiento de Python
frente a código hostil. El comparador es BFS, no un agente LLM.

La dificultad aumentó: G2, sin simulación perfecta, registró0/60 éxitos de
evaluación. Tras introducir libreta exacta de transiciones y exploración de
frontera, G3C alcanzó10/10 en cada uno de dos mapas, con rutas6 y8. En el corredor
usó332 eventos frente a1260 del esquema uniforme anterior que no cerró ruta.
G4 separó herramientas, autoridad y presupuesto: en un6×6 obtuvo10/10 metas
con ruta de10 pasos tras578 acciones de exploración. Esta última cifra es parte
del coste total, no debe ocultarse al mostrar la ruta final.

Procedencia: registro consolidado `lineas_investigacion/protoagente_v3/README.md`,
entradas G1–G5. Los arneses históricos no forman parte de la suite de release.

## SOC persistente y selección de evidencia

D87 ejecutó48 oleadas selladas con tráfico normal, fallas de identidad,
degradación de colector e incidentes compuestos colector+cola. La política no
recibió la etiqueta causal hasta concluir la investigación. Se ejercitó además
un vertical local POS/identidad/SOC SQLite, cambio de contrato, reinicio,
acción verificada y rollback.

| Brazo | Fuentes medias | Fuentes en compuestos | Hipótesis falsas | p95 decisión |
|---|---:|---:|---:|---:|
| Orden fijo |2.73|4.00|0|0.013 ms|
| Contextual |1.67|2.00|0|5.006 ms|
| Runtime |1.67|2.00|0|2.776 ms|
| Tejido |1.67|2.00|0|5.777 ms|

La ganancia contextual es **menos fuentes consultadas**, no menor latencia:
el orden fijo fue más rápido. Runtime y tejido no mejoraron la cantidad frente
al contextual. Los cuatro conservaron servicio crítico, deduplicación,
persistencia, revocación, rollback, auditoría y aislamiento de red del laboratorio.
No se evaluó una red productiva ni se comparó con un analista LLM.

Procedencia: `d87_soc_persistente.md`, campaña
`d87_persistent_soc_campaign/1791433329476495700`,2026-10-07.

## Contención y recuperación de incidentes

La simulación de empresa v2 utilizó Engine/Session dev22 instalados, sin LLM,
seed881 y presupuesto48. El motor eligió entre herramientas; el host escribió
simulador/verificadores, no una secuencia correcta por escenario.

| Escenario | Resultado observado | Decisiones |
|---|---|---:|
| Pérdida masiva simulada |Aisló escritor, restauró datos y verificó transacción nueva.|25|
| Extracción local |Bloqueó nuevos efectos; servicio íntegro.|19|
| Combinado |Contuvo y restauró.|25|
| Backup alterado |Rechazó restauración por integridad.|48|
| Restaurador ausente |Registró capacidad ausente, sin fingir recuperación.|48|
| Sano |Verificó sin contención/restauración innecesarias.|6|

En extracción/combinado habían salido2 filas antes del bloqueo: es **contención
posterior, no prevención de esa fuga**. Una auditoría con canario comprobó que
una fila nueva ya no llegaba al receptor. Hubo acciones excesivas de contención
y peticiones repetidas cuando faltaba restaurador. Las seis misiones conservaron
journals íntegros; el comparador sin agente no recuperó ni contuvo incidentes.
Los efectos son pérdida de filas y receptor SQLite locales, no malware ejecutable.

Procedencia: `framework/INCIDENT_SIM_RESULTADO_V2.md`,
`company-incident-sim-v2` y su auditoría posterior. V1 se preservó como negativo
de implementación; no se mezclan sus resultados con v2.

## Investigación matemática y contraejemplos

La línea usa instrumentos explícitos, hipótesis, búsqueda y verificadores.
Incluye exploración de conjeturas, descarte de afirmaciones inválidas y producción
de certificados finitos; ése es el sentido de «investigación» en estos ensayos.

- **D57:** mínimo de cuadrática convexa, LQR discreto2D por Riccati y certificado
  AM-GM de Motzkin. Cinco semillas por nivel; modo contractual5/5 por nivel,
  sin errores, con4,3 y3 pasos. Las herramientas/precondiciones eran públicas.
- **D58:**18 instancias generadas al ejecutar, dos modalidades y tres familias
  paramétricas. Entrada sin `solution`, `answer`, `method` ni secuencia requerida.
  Ambas modalidades certificaron3/3 por familia. La estructural usó5/4/4 intentos
  totales por familia y0 errores; la exploratoria26/29/30 y5/9/10 errores.
  No hubo LLM, corpus ni red durante resolución. Las familias y operaciones eran
  diseñadas; descubrir una solución paramétrica no equivale a inventar el método.
- **D38:** búsqueda de certificados de resolución PHP y rechazo de certificados
  con referencia futura, pivote inválido, resolvente falso o axioma falsificado.
  En PHP(5,4), orden adaptativo produjo477 pasos frente a6844 del orden fijo.
  En otra familia, ciclos impares, no hubo ventaja. Experimentos posteriores
  de memoria encontraron contraejemplos a su propia promoción y conservaron
  esos negativos en vez de declarar superioridad general.

Procedencia: `d57_math_ladder.md`, `d58_blind_math_discovery.md` y entradas D38 del
registro consolidado de ProtoAgent v3. D58:
`d58/1791262816780359100`,2026-10-05. Algunos trabajos matemáticos del proyecto
también emplearon oráculos externos; no se les atribuye automáticamente el
carácter «sin LLM» de D57/D58. No se afirma resolver problemas abiertos.

## Del laboratorio a la biblioteca pública

La calificación específica rc3 —instalación, cierre de misión, cortes físicos,
autoridad, biblioteca, roles y consumidor asistido— está en
[Technical.md](../Technical.md). Es la evidencia más cercana al software que se
instala hoy; las experiencias anteriores muestran el alcance de la investigación.

Las rutas históricas anteriores son identificadores de procedencia del
laboratorio, no enlaces a archivos incluidos en este repositorio. Este documento
publica resúmenes, no trazas completas ni datasets. Las pruebas reproducibles del
SDK sí están en [tests](../tests/) y sus reportes remotos en
[Actions](https://github.com/Gusmal02/ProtoAgent/actions).

## Comparación honesta con agentes LLM

Se ejercitó ejecución local sin llamadas generativas en los ensayos identificados:
eso implica0 tokens de inferencia del proveedor en esas rutas, independencia de
su conexión/cuota y conservación local de evidencia. No significa coste0 de CPU,
electricidad, herramientas o desarrollo.

No hay aquí un benchmark pareado que iguale tareas, herramientas, presupuesto
y modelos para declarar mayor calidad, menor coste total o menor latencia que
todos los agentes LLM. Los comparadores citados son random walk, BFS, orden fijo,
modalidades estructural/exploratoria y ausencia de agente. Es posible combinar
ProtoAgent con un LLM y también construir controles similares sobre otro framework.
