# Dirección de ProtoAgent: de capacidades verificadas a programación útil

Actualización: **2026-10-17, después de la revisión ciega independiente**.
Base de main:0.1.0rc3; candidata en rama de desarrollo:0.2.0.dev10.
El roadmap registra implementación y evidencia actuales, no sólo propuestas.
No cambia las puertas históricas F8 ni autoriza campañas por sí mismo.

| Hito | Estado actual | Evidencia principal |
| --- | --- | --- |
| H0: SDK y contrato | Implementado y calificado en el alcance publicado. | API, instalación externa, licencia y CI. |
| H1: composición | Implementada para dos entradas. |100/100 reserva y30 regresiones; conserva referencia de seis operaciones. |
| H2: ciclo del motor | Integrado y aprobado. | Generación, contraejemplo QA, reparación, nuevas revisiones, publicación y recuperación tras corte. |
| H3: mantenimiento | Implementado para el proyecto Python/CLI acotado. | Cambios reales en dos módulos, API protegida y adaptación de requisito. |
| H4: reutilización | Recuperación y composición de experiencias verificadas demostradas en el alcance tabular. | Tres programas nuevos con tercera entrada,100/100 cada uno; búsqueda fría agota presupuesto. |
| H5: comunidad | Guía aclarada, revisión ciega positiva condicional conservada y aceptación explícita de Gustavo registrada. | Hash del ejercicio aceptado; no concede aprobación a programas posteriores. |
| Operación sostenida | Perfil v1 dev8 congelado, no activado. | Carga/SLO/recursos/retención fijados; falta supervisor calificado y autorización de corrida. |

La candidata pasó27 pruebas y cuatro perfiles de CI Windows/Ubuntu base/full.
Ese resultado corresponde a dev8. Dev10 pasó30 pruebas instaladas y la
aceptación P1–P3/H4–H5/composición; su CI se registra por commit por separado.
Ver [CI dev8](https://github.com/Gusmal02/ProtoAgent/actions/runs/39046368401),
[P1–P3](docs/PROGRAMACION_P123.md) y [ejercicio comunitario](docs/EJERCICIO_COMUNITARIO.md).

La revisión ciega con GPT-6-Luna, sin historial ni oráculo, es una señal positiva
de comprensión y funcionamiento independiente. Su dictamen fue **condicional**,
no un rechazo funcional ni una aprobación humana. Encontró dos brechas de guía:
semántica de deduplicación/ceros y método para reproducir el hash del artefacto.
La comprobación posterior confirmó que el hash canónico sí coincide: no se
observó alteración del código. Las dos aclaraciones ya se incorporaron a la guía:
reglas precisas, ejemplo manual y comando reproducible del hash. Se comprobaron
el hash, el ejemplo y casos vacío/saldo cero/saldo negativo. Se conserva el
dictamen ciego condicional original; no se inventa una segunda revisión ciega.

## 1. Dirección elegida

**Desarrollar un agente local que pueda investigar, construir y mantener pequeñas
soluciones Python verificables, reutilizando capacidades y recurriendo a un LLM
sólo cuando se decida explícitamente.**

El objetivo no es competir por generar más texto. Es convertir un encargo
comprobable en un artefacto que funcione, superar revisiones, conservar evidencia
y continuar o reparar sin perder autoridad ni presupuesto.

Primer dominio de producto: **datos y automatización Python para una empresa
simulada**, útil para estudiantes y colaboradores de una comunidad. Es la ruta
con más continuidad respecto a las capacidades actuales: transformaciones,
validación de datos, informes, conciliación y servicios locales pequeños.

El SOC y la investigación matemática siguen como consumidores y bancos de
transferencia. No se abren tres productos completos a la vez. El generador
externo permanece como extensión opcional, no atajo para atribuir síntesis al motor.

## 2. Qué tenemos realmente

| Capa | Evidencia disponible | Estado de producto |
|---|---|---|
| SDK | API Python, instalación externa, ejemplos y documentación española. | Público, candidato experimental. |
| Ingeniería de ejecución | Sesiones, recibos, auditoría, presupuesto, revocación, cortes y backup cooperativo. | Calificado en el alcance local documentado. |
| CI | dev8:27 pruebas y cuatro perfiles Windows/Ubuntu base/motor aprobados. | Automatizada, con aceptación P1–P3 y H4–H5. |
| Motor y herramientas | Decide acciones y solicita generación/revisión/publicación en la misión multifichero. | Integración real, repertorio acotado. |
| Constructor tabular | Composición de dos entradas,100/100 reserva y regresiones previas. | Síntesis finita conectada al motor; no Python arbitrario. |
| Calidad | Política robusta:1518/1518 casos frente a1322/1518 de primeras/mínimo en el banco fresco. | Aún separada del decisor resonante. |
| Biblioteca | Recupera código previo para un contrato nuevo, revalida y vuelve a revisar. | Reutilización útil demostrada; sin ventaja temporal contextual frente al catálogo plano en el caso medido. |
| Consumidor independiente | Revisión ciega de IA:20 comprobaciones correctas, dos hallazgos documentales. | Resultado positivo condicional; instalación independiente y revisión humana no cerradas por ese ensayo. |
| Juegos/SOC/matemáticas | Rutas, selección de evidencia, certificados y negativos conservados. | Adaptadores históricos; no todas las capacidades vienen preinstaladas. |

La edición acotada modifica funciones reales y conserva CLI/funciones protegidas.
Gramática, compilador, políticas y verificadores son ingeniería explícita del
host. Mantener esa autoría visible permite saber qué mejoramos realmente.

## 3. Fortalezas que conviene desarrollar

1. **Decisión local sin tokens de inferencia obligatorios.** Adecuada para tareas
   repetidas y recursos limitados; medir CPU/RAM/coste total, no vender coste cero.
2. **Acciones comprobables y autoridad integrada.** Llevar el mismo contrato desde
   solicitud a código, revisión y efecto final; seguridad como criterio de promoción.
3. **Experiencia ejecutable reutilizable.** Convertir experiencias verificadas en
   subprogramas/contratos recuperables, no sólo hashes o contexto para un prompt.
4. **Investigación con retroalimentación.** Usar contraejemplos para cambiar la
   propuesta y conservar el negativo, no repetir intentos equivalentes.
5. **Trabajo durable y colaborativo.** Aprovechar responsables, dependencias y
   revisión por hash para mantener un proyecto, no añadir roles por cantidad.

## 4. Debilidades y acciones prioritarias

Las cuatro primeras brechas se abordaron con P1–P3 para el subconjunto publicado;
no siguen siendo bloqueos idénticos a los del diagnóstico inicial. La expansión
a otros programas y contextos continúa abierta. Esta tabla conserva su trazabilidad.

Dev10 compuso la experiencia anterior con ajustes, reservas y anexado estable
de tercera fuente:300/300 casos reservados. Véase
[composición verificada](docs/COMPOSICION_VERIFICADA.md). Dev9 conserva el negativo
de ordenación; sort_key genérico añadido a ambos brazos, no inventado por el motor.

| Brecha observada | Acción que la cierra | Evidencia de salida |
|---|---|---|
| La poda pierde caminos válidos. | Búsqueda composicional tipada con conservación y reapertura de alternativas. | Resuelve la referencia fallida y mejora coste/éxito en estructuras nuevas. |
| Conciliación multientrada no resuelta. | Representación de dependencias entre tablas/subprogramas, sin helper que resuelva el objetivo. | Programa ejecutado correcto en entradas nuevas, vacías y conflictivas. |
| Generador/calidad/memoria no forman un único ciclo. | Integrar generación→contraejemplo→replan→QA→security→publicación bajo Session. | El motor completa el recorrido con la API instalada; controles y presupuestos intactos. |
| Módulos pegados por compilador fijo. | Edición por funciones/AST y dependencias entre archivos en un repositorio existente. | Cambio funcional real sin reemplazar el proyecto por una plantilla. |
| Preferir código barato puede aceptar código incorrecto. | Corrección/seguridad primero; después frontera de robustez, coste y simplicidad. | Varias soluciones válidas comparadas y elección justificada. |
| Memoria puede sugerir fuera de contexto o no transferir. | Condiciones de validez y revalidación; evaluar frío/caliente/memoria incompatible. | Reutilización útil o abstención; sin admitir herramienta incompatible. |
| Roles no garantizan coordinación eficaz. | Builder entrega, QA mide funcionalidad, Security valida frontera; dependencia real entre ellos. | Mismo presupuesto total, menos retrabajo o mayor calidad atribuible al protocolo. |
| Código arbitrario no está aislado. | Conservar primitivas confiables hoy; diseñar aislamiento real antes de aceptar código hostil. | Política de proceso/archivos/red/recursos verificada, no sólo AST o `-I`. |

## 5. Hitos secuenciales

### H0 — Baseline única y contrato de programación

Reconocer como cerrados API/instalación/Apache/consumidor asistido/CI inicial;
no repetirlos como una nueva fase de investigación. Identificar interfaces que
ya existen: `generate(identity, contract, feedback)`, `ProgrammingRuntime`,
`Session`, registro de herramientas y verificadores. Extenderlas sin duplicar kernel.

Congelar qué significa «programar mejor»: modificar funciones Python y componer
transformaciones verificables dentro de un proyecto pequeño, con requisitos y
ejemplos pero sin solución, ruta óptima ni parche prediseñado.

**Salida:** manifest de versión, alcance soportado, contrato y presupuesto total.
No requiere una campaña larga ni ampliación del motor.

### H1 — Composición y replanificación del constructor

Primero cerrar selección y conservación de estados intermedios. Representar
subprogramas por tipos, entradas/salidas y dependencias. Una coincidencia en
pocos ejemplos no prueba equivalencia universal: usar contraejemplos y limitar
la deduplicación al alcance comprobado. Cobrar sondeos, búsqueda y verificaciones.

Primitivas nuevas sólo ante ausencia real de capacidad; no añadir una macro
que contenga la solución del encargo evaluado. La búsqueda debe poder separar
`capability_missing`, `search_exhausted`, `invalid_candidate` y `unsafe_candidate`.

**Salida:** referencia de seis operaciones y conciliación de dos entradas
resueltas; sin perder los encargos anteriores dentro de su contrato. Comparación
con backend congelado y reserva nueva para evitar sobreajuste a esos dos casos.

### H2 — Programación de extremo a extremo decidida por el motor

Conectar constructor, feedback, biblioteca y selección de calidad a una misión
real. Si falla un candidato, el motor solicita una alternativa, una herramienta
faltante o se abstiene con motivo; no reenvía la misma petición indefinidamente.
El host expone capacidades, no un scheduler oculto de la solución.

QA ejecuta pruebas funcionales; Security comprueba permisos, acceso a archivos,
entradas, imports y efectos permitidos. La misma revisión se liga al hash que
se publica. Reutilizar el protocolo existente y extender sólo la brecha necesaria.

**Salida:** ciclo completo sobre paquete instalado, incluida una recuperación
intermedia y una revocación; sin efecto indebido ni presupuesto reiniciado.

### H3 — Proyectos Python y mantenimiento de código

Pasar de emitir archivos con cableado fijo a modificar funciones y contratos de
un proyecto existente: transformación de datos + validador + informe/CLI.
Después introducir un servicio HTTP local pequeño, como adaptador independiente.
No empezar por frontend, nube y despliegue completo a la vez.

**Salida:** cambio multifichero que implementa un requisito nuevo, conserva API y
regresiones, y repara un defecto con evidencia sin ancla de parche predefinida.
Código existente/solución del evaluador quedan fuera del corpus del constructor.

### H4 — Aprendizaje operativo reutilizable

**Estado:** reutilización de código completo demostrada en dev8. Tres brazos
aciertan100/100; sin memoria se exploran8055 candidatos y con memoria ninguno,
añadiendo16 comprobaciones de recuperación y revisiones actuales. Preparación
común:31074 candidatos y636444 operaciones-fila. No se atribuye coste cero.
No hubo ventaja temporal del descriptor frente al catálogo plano; no se necesita
repetir este ensayo para reconocer el avance. Próxima ampliación: componer o
adaptar capacidades ante operaciones realmente diferentes, con banco nuevo.

Guardar sólo subprogramas de trayectorias reales y verificadas. Medir si ayudan
en nuevos contratos bajo el mismo catálogo y presupuesto; comparar sin memoria,
catálogo plano y biblioteca contextual. No atribuir macros de un solver privado
al agente. Un resultado negativo conserva la biblioteca como infraestructura,
sin presentarlo como aprendizaje demostrado.

**Salida:** menor trabajo total o mayor éxito en tareas reservadas, sin aumentar
aceptaciones incorrectas. Reinicio/revisión de contrato no recuperan autoridad antigua.

### H5 — Producto comunitario y operación sostenida

**Estado:** ejercicio y mecanismo de entrega/revisión disponibles. La revisión
ciega independiente dio evidencia funcional positiva y dos condiciones de guía.
No repetir otro benchmark masivo para corregir esos puntos: aclararlos y comprobar
sus ejemplos/instrucciones. Después, uso por una persona y preparación operativa.
La revisión artificial se conserva como evidencia propia, sin etiquetarla humana.

Ofrecer ejercicios de la empresa simulada, plugins/adaptadores confiables,
plantillas de contratos y revisión externa humana. Mantener matrices de CI,
vulnerabilidades, migraciones, release y contacto privado de seguridad.

Sólo después de congelar una carga útil y SLO/retención/recursos/incidentología,
considerar la campaña autorizable de ocho horas. No arrancarla desde este plan.
Los ejercicios SOC iniciales son de observación/propuesta o canario autorizado.

## 6. Evaluación: menos campañas, decisiones más claras

Preparar un **único plan de evaluación incremental**, no una sucesión de demos
atómicas. Antes de ejecutar, fijar banco de desarrollo, casos de regresión y
reserva terminal sin feedback. Separar estructuras de semillas y no aumentar
presupuesto ni cambiar requisitos al descubrir un fallo.

Comparadores sobre las mismas herramientas/entradas: backend actual, backend
composicional y motor integrado. La primera comparación identifica el avance
de síntesis; la segunda comprueba el aporte del agente. LLM opcional sólo en
un brazo separado con nueva autorización de proveedor/coste, no como requisito.

Medir por encargo:

- Corrección reservada, compatibilidad, robustez e invariantes de seguridad.
- Calidad: entradas límite, efectos secundarios, duplicación/dependencias y tamaño
  del cambio; no usar líneas de código como única medida de mantenibilidad.
- Trabajo total: búsqueda, compilación, pruebas, revalidación, mensajes y reintentos.
- Latencia hasta objetivo, CPU, memoria de proceso y crecimiento de disco.
- Autoría y decisiones: qué construyó el backend, qué eligió el motor y qué dio el host.

**Seguridad y corrección son puertas, no puntos compensables con velocidad.**
No promover una solución rápida que publica sin permiso. Un fallo válido de
capacidad no dispara repeticiones ilimitadas. Al aparecer un bloqueo común,
detener la expansión del banco, diagnosticar y conservar la versión negativa.

## 7. Qué no priorizar ahora

- Más roles, primitivas o nodos sin una brecha concreta que lo justifique.
- Un benchmark de miles de pares antes de arreglar composición y selección.
- Presentar resultados de laboratorio como funciones listas del SDK.
- Programación libre desde lenguaje natural como requisito inmediato del motor local.
- Reabrir E1–E3, promover F8 integral o iniciar8h/24h/72h por actualizar este documento.

## 8. Próximos pasos, en orden

1. **Completado: aclaraciones de la revisión ciega.** La guía especifica
   duplicados/positivos/ceros y cálculo del hash canónico. Comando y ejemplo
   comprobados, sin repetir las campañas aceptadas ni modificar el runtime.
2. **Completado: aceptación del ejercicio por Gustavo.** Se registró su mensaje
   explícito «lo acepto» ligado al hash dev8. La reproducción integral por más
   usuarios sigue siendo una futura ampliación comunitaria. Una persona sigue el ejercicio, revisa la entrega
   y registra aceptar/rechazar con sus motivos. La aprobación automática y la
   revisión ciega de IA ya realizadas no se descartan ni se confunden con esto.
3. **Completada la preparación v1, sin activar:** paquete dev8, carga, duración, SLO,
   recursos, retención, cancelación e incidentes según la
   [puerta operativa](docs/OPERACION_SOSTENIDA.md). Revisar promoción de main
   por separado; no desplegar ni arrancar ocho horas desde este documento.
4. **Implementado y evaluado en dev10:** reutilización composicional/adaptativa
   para operaciones distintas y proyectos más diversos, sin perder la regresión
   ya aprobada. Código hostil exige aislamiento real antes de admitirlo.

## Referencias y estado de decisiones

Base del diagnóstico: informes del laboratorio `TYPED_FRONTIER_RESULTADO`,
`TYPED_EXPANSION_RESULTADO`, `DEEP_SYNTHESIS_RESULTADO`, `QUALITY_SYNTHESIS_RESULTADO`,
`QUALITY_BENCHMARK_RESULTADO` y `V01_RELEASE_RESULTADO`. Son referencias de procedencia,
no archivos distribuidos automáticamente. Ver [Technical.md](Technical.md) y
[Experimentos](docs/EXPERIMENTOS.md) para el resumen público.

El roadmap de2026-10-13 de entrega del framework queda como historial; ya no
describe pendientes de publicación/CI. Éxitos nuevos no borran sus negativos ni
aprueban retroactivamente sus criterios científicos.
