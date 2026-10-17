# ProtoAgent Framework

**Agentes locales con memoria, trabajo verificable y permisos explícitos. Sin
necesitar un modelo de lenguaje para ejecutar sus funciones locales.**

ProtoAgent es una biblioteca de Python para construir programas que observan
un entorno, eligen entre herramientas disponibles, ejecutan trabajo y comprueban
si alcanzaron un objetivo. Guarda el avance para que una tarea no dependa
solamente de lo que queda en memoria mientras el programa está abierto.

Su intención es unir tres cosas: **decidir con evidencia, conservar experiencia
utilizable y actuar sólo con autorización**. Esto permite desarrollar y estudiar
agentes sin hacer una llamada a un servicio generativo en cada paso.

Versión actual: **0.1.0rc3, candidata experimental**, licencia **Apache-2.0**.
No es todavía un servicio listo para producción ni un programador general.

## ¿Para qué puede servir?

Para desarrollar ejercicios, prototipos y automatizaciones locales controladas,
por ejemplo:

- Preparar y registrar un informe de calidad de datos con trazabilidad.
- Dar seguimiento a una tarea y recuperar su avance después de cerrar el programa.
- Coordinar entregas: Data prepara un artefacto, QA lo revisa y DevOps recibe
  únicamente la versión aprobada.
- Conservar herramientas verificadas y volver a comprobarlas antes de reutilizarlas.
- Estudiar decisiones, errores y consumo de recursos con un presupuesto limitado.

Estos usos requieren conectar herramientas y verificadores apropiados. La
biblioteca no trae un experto universal de Data, QA, DevOps o ciberseguridad.

## ¿Qué ofrece actualmente?

| Capacidad | Qué significa para quien la utiliza |
|---|---|
| Motor de decisión local | Selecciona acciones dentro de las posibilidades que la aplicación le ofrece. |
| Sesiones persistentes | Conserva avance, presupuesto e historial de la misión. |
| Herramientas conectables | Puedes conectar funciones Python mediante una API pública, sin editar el motor. |
| Memoria contextual | Recupera información asociada a una entidad y revisión, sin tratarla como permiso. |
| Biblioteca de herramientas | Registra, recupera y revalida capacidades ejecutables verificadas. |
| Trabajo por roles | Define responsables, dependencias y revisión de entregas por su contenido exacto. |
| Control de autoridad | Una autorización revocada no debe convertirse en un nuevo efecto permitido. |
| Evidencia y auditoría | Permite inspeccionar resultados y comprobar la integridad del historial. |

La recuperación segura necesita que la herramienta conectada también guarde
sus efectos y recibos correctamente. No basta con instalar ProtoAgent para
volver segura cualquier API externa.

## ¿Necesito un LLM o una API key?

**No para los ejemplos y funciones locales documentadas aquí.** El motor local
no es un LLM pequeño ni interpreta libremente cualquier instrucción en lenguaje
natural. Trabaja con objetivos, observaciones y acciones estructuradas.

Hay módulos experimentales de generación y conectores externos. No se usan en
la guía inicial. La síntesis actual está acotada: no prometemos que genere
cualquier aplicación, aprenda Python leyendo documentación o descubra por sí
solo una estrategia general.

## Empieza aquí

Necesitas **Python 3.12**, una terminal y una carpeta de trabajo. Si estas
palabras son nuevas para ti, sigue la [guía desde cero](docs/USO.md): explica
la instalación, qué copiar, qué resultado esperar y cómo resolver errores.

Si ya usas Python:

```console
git clone https://github.com/Gusmal02/ProtoAgent.git
cd ProtoAgent
python -m venv .venv
```

Activa el entorno según tu sistema, como indica la guía, y ejecuta:

```console
python -m pip install ".[motor]"
python examples/local_counter.py --workspace ./counter-demo
```

El ejemplo intenta llevar un contador local hasta 2. Un resultado correcto
incluye `"status": "completed"`, `"value": 2` y `"audit": true`.
Usa una carpeta nueva si quieres repetirlo. **No requiere credenciales ni
conexión a un LLM.** La instalación inicial sí puede descargar dependencias.

También existe una instalación básica más ligera: `python -m pip install .`.
Sirve para los ejemplos de memoria y protocolo de colaboración; el motor y
la biblioteca numérica requieren la opción `[motor]`.

## API pública y consumo independiente

Sí: la API se importa como `protoagent_framework`. Es una **API Python/SDK**,
no un servidor REST ni una página web. Un usuario puede instalar el paquete,
usar las clases públicas y conectar sus funciones sin consultar archivos
internos ni modificar el motor.

Un consumidor ciego asistido integró un dominio propio de cola de tareas usando
documentación y API públicas. Completó una misión, reabrió una sesión a mitad
del trabajo y comprobó presupuesto, duplicados y revocación. Esa revisión
también permitió corregir ambigüedades de documentación.

## ¿Qué se ha comprobado?

La candidata pasó pruebas locales de instalación, finalización, persistencia,
recuperación tras cortes, permisos, biblioteca y colaboración. En la suite
consolidada aprobaron **18 pruebas completas** y **13 del perfil básico**.

Una regresión multifichero aprobó **543 comprobaciones** y completó la misión
después de corregir un problema de cierre. Es una prueba concreta, no 543
problemas diferentes. El detalle, métricas, interpretación y límites están en
[Technical.md](Technical.md).

El estado de las verificaciones automáticas se puede consultar en
[GitHub Actions](https://github.com/Gusmal02/ProtoAgent/actions). Una prueba
aprobada no certifica todos los equipos, sistemas operativos o cargas futuras.

## Documentación

- [Guía de uso desde cero](docs/USO.md): instalación y primeros programas.
- [Referencia pública de API](docs/API.md): clases, contratos y errores.
- [Technical.md](Technical.md): arquitectura, metodología y resultados.
- [Seguridad](SECURITY.md): qué protege el framework y qué debe proteger tu aplicación.
- [Contribuir](CONTRIBUTING.md): cómo proponer mejoras y reproducir comprobaciones.
- [Historial de cambios](framework/distribution/CHANGELOG.md).

## Uso responsable y comunidad

Empieza con datos sintéticos y funciones locales de confianza. No ejecutes
código desconocido dentro del proceso ni lo expongas directamente a Internet.
ProtoAgent no ofrece aislamiento del sistema operativo, defensa universal
contra ataques ni recuperación garantizada de ransomware.

Queremos que otras personas puedan aprender, integrar herramientas, encontrar
fallos y contribuir con ejemplos reproducibles. Puedes abrir una propuesta o
reporte en [Issues](https://github.com/Gusmal02/ProtoAgent/issues); **no publiques
allí claves ni detalles explotables de una vulnerabilidad**. Lee primero la
política de seguridad.

El código del SDK y sus fuentes incluidas se distribuyen bajo
[Apache-2.0](LICENSE). Las dependencias conservan sus propias licencias y avisos;
consulta [NOTICE](NOTICE).
