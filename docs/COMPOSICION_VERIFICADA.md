# Componer una capacidad anterior para resolver un encargo distinto

La candidata0.2.0.dev10 añade `AdaptiveReuseGenerator`, que utiliza expresiones
de trayectorias realmente generadas, ejecutadas y aprobadas por QA/Security.
El DAG histórico debe recompilar exactamente al código verificado: no se acepta
una macro aportada por el evaluador ni IR modificada sin respaldo.

En vez de recuperar el programa completo sin cambios, la búsqueda puede tomarlo
como subprograma y combinarlo con operaciones y una tercera entrada. Los ejemplos
del nuevo contrato guían selección; no incluyen el programa ni el oráculo.
Cada evaluación cobra el tamaño del programa completo y una reserva conservadora
de trabajo por filas. Nuevos programas necesitan nuevas revisiones.

## Qué se comprobó

Se aprendió operativamente una conciliación de dos tablas (experiencia ejecutable,
no reentrenamiento). Después se compuso con una tercera tabla para:

- Sumar ajustes agrupados al saldo.
- Restar reservas agrupadas al saldo.
- Anexar registros preservando duplicados y ordenar establemente por cuenta.

Los tres programas contienen el DAG previo y pasaron100 casos reservados cada
uno. La búsqueda fría con las mismas primitivas agotó el presupuesto en los
tres encargos. Preparación común:15537 candidatos/318222 operaciones-fila y
nueve despachos. No se borra ese coste ni se llaman tres dominios independientes.

Dev9 pasó los dos primeros y agotó presupuesto en el tercero. Su sort disponible
ordenaba por cuenta e importe; faltaba orden estable sólo por cuenta. Dev10
incorpora `sort_key`, primitiva genérica disponible en AMBOS brazos. Se mantiene
el contrato, el presupuesto y el negativo anterior. Esta primitiva es ingeniería
del desarrollador, no una invención del agente.

## Reproducir

Con la candidata instalada en Python3.12 y extra `[motor]`, desde su código:

```console
python -I tools/adaptive_campaign.py ./composicion --support tests/p123_support.py --evaluator tests/adaptive_support.py
```

Usa carpeta nueva. Son misiones secuenciales, con180s de límite global. Resultados
y negativos quedan guardados; `search_budget_exhausted` del brazo frío no prueba
imposibilidad matemática. La reserva no devuelve feedback al constructor.

## API y seguridad

`from protoagent_framework.adaptive_synthesis import AdaptiveReuseGenerator`.
Inicialización igual que `CapabilityReuseGenerator`: base SQLite, biblioteca,
callback confiable de verificación y modo `off`/`contextual`.

Para dos entradas conserva el constructor previo. Para tres, usa búsqueda
composicional con experiencias compatibles por columnas y dependencias. Sólo
se guardan IR de resultados propios que coinciden con el hash revisado; se
comprueban vigencia de biblioteca y compilación antes de utilizarlas.

La gramática, compilador, primitivas y política son explícitos. No es Python
libre ni aprendizaje resonante de nuevos operadores. El repertorio está limitado
a tablas tipadas y hasta32 nodos de DAG; no ejecuta plugins hostiles. La entrega
humana aceptada de dev8 y su perfil operativo siguen congelados por separado.
