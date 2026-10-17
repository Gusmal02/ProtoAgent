# ProtoAgent Framework — candidata0.1.0rc3

SDK Python local para decisiones del motor, sesiones durables, herramientas
verificadas, memoria contextual y colaboración por roles. Licencia Apache-2.0.
Los ejemplos locales no requieren LLM ni API key.

Esta candidata es experimental. No es un servicio de producción, una sandbox
para código hostil ni un programador general. El SDK base usa la biblioteca
estándar; el extra `[motor]` añade NumPy, Torch y NetworkX. Requiere Python3.12.

## Documentación en español incluida en la fuente

- [Presentación y capacidades](../../README.md).
- [Uso desde cero](../../docs/USO.md): instalación, terminal, ejemplos y errores.
- [API pública](../../docs/API.md): contratos y callbacks.
- [Technical.md](../../Technical.md): arquitectura, pruebas y resultados.
- [Seguridad](../../SECURITY.md) y [contribución](../../CONTRIBUTING.md).

Desde una copia del repositorio, crea un entorno virtual e instala con
`python -m pip install .` o `python -m pip install ".[motor]"`.
Con un wheel descargado, sustituye el punto por la ruta real del archivo.
No se anuncia publicación en PyPI. La instalación inicial puede descargar
dependencias; los ejemplos no hacen llamadas a modelos externos.

La API se importa como `protoagent_framework`, no como `core` o `f8_next`.
No se instala servidor ni servicio de fondo. Las sesiones y stores deben cerrarse
en `finally`. Información y hashes no otorgan permisos. Un host confiable debe
registrar herramientas/verificadores y revalidar autoridad antes de ejecutar.

El wheel incluye SDK, clausura del motor/biblioteca y licencia/NOTICE. La fuente
incluye además documentación, ejemplos, tests y CI; no incluye datasets privados,
claves ni resultados voluminosos del laboratorio.

La versión fue calificada localmente en Windows x64/Python3.12. Consulta
[Actions](https://github.com/Gusmal02/ProtoAgent/actions) para resultados de la
matriz remota Windows/Ubuntu por commit; los demás entornos no se presumen probados.

Los generadores y transporte externo son experimentales. No prometemos Python
libre, transferencia general, superioridad universal de equipos, operación8h
calificada ni exactly-once remoto. Las garantías durables exigen proveedores
locales cooperativos y límites de confianza expresos.
