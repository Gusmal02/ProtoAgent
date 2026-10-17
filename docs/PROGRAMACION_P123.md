# Programación composicional — candidata0.2.0.dev7

Extensión experimental del SDK rc3. Sin LLM ni servicios externos. La línea
P1–P3 une construcción por búsqueda finita, decisión del motor y modificación
de funciones de un proyecto existente. No sustituye rc3 establecida en main
hasta completar revisión/calificación de la candidata.

## Qué se implementó

- `CompositionalSynthesizer`: conserva subprogramas de ramas independientes y
  combina por restricciones algebraicas genéricas. Las coincidencias sobre
  ejemplos no se consideran equivalencia universal; un contraejemplo reconstruye
  las clases de búsqueda. Esta versión resuelve dos entradas; tres requieren
  ampliación y no se reportan como soportadas.
- `CompositionalGenerator`: puerto `generate(identity, contract, feedback)` con
  intención/resultado SQLite, replay y coste acumulado. Un intento interrumpido
  sin resultado bloquea trabajo nuevo hasta reconciliación; no se reinicia budget.
- `ProgrammingRuntime`: integra resultados tipados, QA, Security, generación,
  reparación y publicación. Ofertas de revisión/replanificación son entradas
  confiables congeladas con la sesión, no permisos ni una secuencia de turnos.
- `project_editing`: reemplazo AST de funciones admitidas y publicación en una
  carpeta nueva, conservando CLI y funciones protegidas. Hash base y revisión
  vigente obligatorios. El marcador de aprobación se escribe al final.

La política de obligaciones/replanificación es diseñada explícitamente. El motor
elige entre obligaciones disponibles, reparación directa o delegada y publicación
verificada. No se presenta como planificación emergente aprendida. La gramática,
compilador, política y verificadores son ingeniería Codex; los programas se
seleccionan mediante búsqueda durante la ejecución.

## Evidencia P1–P3

Calificación local instalada de dev7: 24 pruebas unitarias, conformidad y
aceptación integrada aprobadas en 56,19 s. Perfil mínimo sin motor aprobado
en 5,42 s. Aceptación P1→P2→P3, incluidos arranques y corte: 16,96 s.
Estos tiempos describen esta ejecución Windows/Python 3.12, no un SLO.

P1 encontró una conciliación multientrada que el backend previo no resolvió en
su frontera; el código emitido pasó100/100 casos reservados. La referencia
unaria de seis operaciones permaneció correcta en30 regresiones. Entre tres
variantes compatibles se eligió menor trabajo por filas: es proxy declarado,
no prueba de menor CPU ni de mantenibilidad general.

P2 produjo un candidato, recibió un contraejemplo real de QA, reparó el código,
obtuvo revisiones del nuevo hash y publicó. Se realizó un corte físico después
del recibo de generación y antes del checkpoint: la reanudación no regeneró el
resultado ya comprometido. El artefacto pasó100/100 casos reservados.

P3 modificó `transforms.py` y `validation.py` de un proyecto existente, preservó
su CLI y funciones protegidas, ejecutó la CLI y publicó el resultado. Una segunda
misión adaptó el contrato para incluir grupos de venta con valor cero y publicó
la revisión; pasó otros100 casos y cuatro regresiones de borde. Una publicación
con permiso revocado fue rechazada sin crear salida.

Las reservas son variaciones del dominio tabular, no100 familias distintas.
El segundo encargo demuestra mantenimiento ante cambio de requisito; no se
afirma reparación arbitraria de cualquier bug de Python. Los resultados completos
de cada sistema/commit están en los artefactos de CI cuando esa ejecución termine.

## Reproducir

Instala el wheel de esta candidata con `[motor]` en un entorno separado y ejecuta:

```console
python -I tools/p123_campaign.py ./reporte-p123 --support tests/p123_support.py
```

Usa carpeta nueva. El controlador ejecuta P1→P2→P3 secuencialmente, conserva
manifest/logs/resultados y se detiene si una fase falla. Cada fase tiene120s de
deadline; incluye un corte de proceso propio deliberado y una reanudación P2.
No detiene otras aplicaciones. El test requiere datos sintéticos y no usa red.
El gate completo también ejecuta esta campaña como aceptación del paquete.

Entradas: claves públicas `key`, `value`, `inputs`, `branch_depth`, `examples`
y opcional `project_files`. Ejemplos contienen `input`/`output`. No recibe
el oráculo ni el código objetivo. Los estados de agotamiento no prueban
imposibilidad matemática. Búsqueda y reintentos comparten techo de200000
candidatos,12M operaciones-fila reservadas y20s de búsqueda por encargo.

## Biblioteca y seguridad

La biblioteca opcional registra código revisado y lo puede recuperar/materializar
y revalidar bajo el mismo contrato. Recuperación contextual no demuestra todavía
transferencia ni aporta autoridad. QA/Security siguen siendo necesarios.

Sólo se ejecuta código del compilador confiable y fixtures del host. AST y `-I`
no son una sandbox. La publicación de varios archivos no es una transacción
atómica del filesystem: una carpeta sin marcador no es entrega completa y no se
sobrescribe silenciosamente. No hay soporte para plugins hostiles ni rutas
arbitrarias. Ver [SECURITY.md](../SECURITY.md).

Negativos preservados: primera búsqueda agotó presupuesto; replay inicial tenía
tuplas frente a listas JSON; el motor inicialmente se abstuvo antes de reparar
y, después, no repitió QA tras cambiar el artefacto. Nuevas versiones cerraron
esas brechas sin eliminar abstención, subir presupuesto ni editar históricos.
