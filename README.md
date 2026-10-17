# ProtoAgent Framework

### Decidir, explorar y coordinar con memoria y evidencia. Sin depender de un LLM en cada paso.

**ProtoAgent es un motor de agentes locales para convertir observaciones en
acciones verificables.** Combina decisión, memoria de experiencia, exploración
de alternativas y control de autoridad en una biblioteca de Python.

El proyecto nace de la investigación del **Campo de Memoria Resonante**: una
arquitectura que representa experiencias y señales de novedad mediante dinámica
de campos. Esa línea evolucionó hacia agentes capaces de interactuar con
entornos, utilizar herramientas, investigar posibilidades y conservar su trabajo.

**De resolver rutas en juegos a investigar incidentes de un SOC o explorar
problemas matemáticos:** la idea es que un agente pueda hacer trabajo útil con
herramientas, memoria y verificadores, sin necesitar una conversación generativa
para decidir cada movimiento.

**Python 3.12 · Ejecución local · API pública · Apache-2.0**

[Empezar desde cero](docs/USO.md) · [Resultados y experimentos](docs/EXPERIMENTOS.md) ·
[Detalle técnico](Technical.md) · [Referencia API](docs/API.md)

## ¿Qué puedes construir con ProtoAgent?

- **Agentes de exploración:** recorrer estados, comparar alternativas, registrar
  intentos y aprovechar evidencia de lo que funcionó o resultó un callejón sin salida.
- **Asistentes de investigación:** conectar instrumentos matemáticos o computacionales,
  probar hipótesis, buscar contraejemplos y entregar resultados a un verificador.
- **Operadores locales:** observar una aplicación, investigar incidencias y seleccionar
  acciones autorizadas de contención, restauración o comprobación.
- **Equipos con responsabilidades claras:** Data produce una entrega, QA revisa su
  contenido exacto y DevOps recibe el artefacto aprobado, con dependencias y permisos.
- **Automatizaciones que conservan el avance:** pausar, reabrir y continuar una misión
  con su presupuesto, historial y recibos de operaciones.
- **Bibliotecas de capacidades reutilizables:** registrar herramientas verificadas,
  recuperarlas según su contexto y revalidarlas antes de utilizarlas otra vez.

Tú conectas el entorno, las herramientas y los criterios de aceptación.
ProtoAgent aporta el motor de decisión y las interfaces de memoria, continuidad
y gobernanza para trabajar con ellos.

## Más que una demostración con un contador

La trayectoria experimental del proyecto incluye varios dominios:

| Dominio | Qué se puso a prueba | Resultado destacado |
|---|---|---|
| **Juegos y navegación** | Laberintos, planificación de rutas y exploración en FrozenLake. | En un ensayo 5×5 llegó en 10 pasos frente a 71 de media del recorrido aleatorio; en FrozenLake determinista con simulación reversible alcanzó 12/12 metas y empató las rutas mínimas de los tres mapas. |
| **SOC e investigación de incidentes** | Correlación de evidencia, fallos de identidad/colector, incidentes compuestos, contratos y recuperación. | En 48 oleadas, la estrategia contextual consultó 1.67 fuentes de media frente a 2.73 del orden fijo, sin hipótesis falsas registradas; se verificaron reinicio, revocación y rollback locales. |
| **Continuidad de una empresa simulada** | Pérdida de datos, extracción local, restauración y comprobación posterior. | El motor seleccionó contención/restauración/verificación en los tres escenarios recuperables; ante backup alterado rechazó restaurar. |
| **Exploración matemática** | Hipótesis, búsqueda de contraejemplos, selección de instrumentos y certificados. | Ensayos sin LLM resolvieron instancias paramétricas de cuadráticas, control LQR y certificados AM-GM para polinomios tipo Motzkin, con verificación de resultados. |
| **Código y herramientas** | Generación acotada, revisión QA/security y publicación verificable. | Una misión multifichero completó su ciclo y aprobó 543 comprobaciones funcionales y de seguridad locales. |
| **Integración por terceros** | Uso de API pública sin modificar el núcleo. | Un consumidor ciego asistido integró una cola de tareas y verificó reapertura, presupuesto, replay y revocación. |

Son hitos de **distintas versiones y adaptadores de investigación**, no una lista
de aplicaciones preinstaladas en el SDK. La versión pública reúne el núcleo y
las interfaces para desarrollar integraciones. El [registro de experimentos](docs/EXPERIMENTOS.md)
explica configuraciones, comparadores y procedencia de cada resultado.

## ¿Qué ventaja aporta frente a un agente que consulta un LLM en cada paso?

### 1. Cero tokens de inferencia en la ruta local

El motor puede observar, decidir y ejecutar sin llamar a un modelo generativo.
**No hay facturación por tokens del proveedor para esas decisiones.** Es una
ventaja práctica cuando necesitas repetir muchas operaciones o tienes un
presupuesto limitado. El cómputo, la memoria y las herramientas locales sí tienen coste.

### 2. Funcionamiento independiente de un servicio generativo

Una vez instalado y con herramientas locales, puede operar sin conectividad a
un proveedor LLM. El ciclo de decisión no depende de su cuota, disponibilidad
o tiempo de respuesta. Esto resulta útil en laboratorios, simulaciones y
automatizaciones locales que deben seguir trabajando.

### 3. Memoria que se puede usar y verificar

Conserva estado, referencias, experiencias y herramientas con sus condiciones
de validez. El trabajo puede continuar entre sesiones, y la evidencia puede
influir en selecciones posteriores. En el ensayo SOC, la recuperación contextual
redujo las fuentes consultadas frente al orden fijo.

### 4. Acciones sujetas a permisos y resultados comprobables

Una propuesta no equivale a una autorización. La aplicación puede exigir
revisión, contexto vigente, presupuesto y verificación antes de aceptar efectos.
Esto permite diseñar agentes donde «lo dijo el modelo» no sea el criterio de éxito.

### 5. Una base que también admite colaboración con LLM

Puedes reservar un modelo externo para tareas en las que aporte valor, como
solicitar código o interpretar lenguaje, y mantener ejecución, permisos y
verificación bajo control local. Esa integración es opcional: los ejemplos
iniciales funcionan sin API key.

Estas ventajas describen el **modelo de operación** y mecanismos ejercitados.
No presentamos un benchmark pareado que demuestre mayor calidad general que
agentes LLM, ni que otros frameworks sean incapaces de implementar controles similares.

## Cómo trabaja

```text
Observar → consultar memoria → evaluar alternativas → actuar → verificar
                              ↑                           |
                              └──── conservar evidencia ──┘
```

- El **motor** selecciona acciones entre las capacidades disponibles.
- La **sesión** guarda avance, presupuesto e historial.
- Las **herramientas** conectan el agente con el trabajo real de tu aplicación.
- La **memoria y biblioteca** conservan información y capacidades reutilizables.
- Los **contratos y verificadores** delimitan qué puede hacer y cómo comprobarlo.

La API se importa como `protoagent_framework`. Puedes utilizarla desde tu
aplicación Python sin modificar el motor ni acceder a tablas internas.

## Empieza en tu equipo

Versión actual: **0.1.0rc3, candidata experimental**.
Necesitas **Python 3.12**. Si nunca has instalado una biblioteca, sigue la
[guía paso a paso](docs/USO.md), con instrucciones para Windows y Linux.

```console
git clone https://github.com/Gusmal02/ProtoAgent.git
cd ProtoAgent
python -m venv .venv
```

Activa el entorno como indica la guía y ejecuta:

```console
python -m pip install ".[motor]"
python examples/local_counter.py --workspace ./counter-demo
```

El contador es una **primera comprobación de instalación**, no la frontera de
capacidad del proyecto. El resultado esperado incluye:

```json
{"status": "completed", "value": 2, "audit": true}
```

Usa una carpeta nueva para repetirlo. También puedes probar memoria e informes
con `examples/referenced_data.py`, o el protocolo de colaboración con
`examples/collaboration_data_ops.py`. Estos dos ejemplos admiten el perfil básico
`python -m pip install .`, sin dependencias numéricas.

## Una entrega comprobable

La candidata pública cuenta con **18 pruebas completas**, **13 del perfil
básico**, **273 controles de gobernanza por perfil** y ejemplos ejecutables.
La CI inicial aprobó los cuatro perfiles de Windows/Ubuntu, con y sin motor.
Consulta las [ejecuciones de CI](https://github.com/Gusmal02/ProtoAgent/actions).

En la entrega se comprobaron finalización de misión, recuperación tras cortes,
integridad, permisos, biblioteca, colaboración e instalación limpia. La
[documentación técnica](Technical.md) detalla cómo se evaluaron y qué significa
cada cifra.

## Estado y alcance

ProtoAgent es una plataforma experimental en desarrollo. Su fortaleza actual
está en objetivos estructurados, herramientas conectadas y verificación explícita.
La programación general y la comprensión abierta del lenguaje son líneas distintas
de la ejecución local. Las pruebas SOC son de laboratorio, no una certificación
de defensa de producción. Para integrar recursos importantes, lee [Seguridad](SECURITY.md).

## Participa

Queremos facilitar que personas con recursos limitados experimenten con agentes,
simulaciones laborales, investigación y automatización verificable. Puedes aportar
un adaptador, un caso de uso, una prueba reproducible o una mejora de documentación.

- [Guía de uso](docs/USO.md) y [API pública](docs/API.md).
- [Arquitectura y resultados técnicos](Technical.md).
- [Experimentos por dominio](docs/EXPERIMENTOS.md).
- [Cómo contribuir](CONTRIBUTING.md) e [Issues](https://github.com/Gusmal02/ProtoAgent/issues).

Licencia [Apache-2.0](LICENSE). Consulta [NOTICE](NOTICE) para atribución y
dependencias. No publiques secretos ni detalles explotables en una Issue pública.
