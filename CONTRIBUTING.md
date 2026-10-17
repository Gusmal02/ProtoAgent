# Cómo contribuir

Gracias por ayudar a mejorar ProtoAgent. Puedes proponer documentación, ejemplos,
adaptadores, correcciones o pruebas reproducibles. Usa datos sintéticos y respeta
la [política de seguridad](SECURITY.md).

## Antes de modificar código

1. Sigue la [guía inicial](docs/USO.md) con Python3.12 y un entorno virtual.
2. Comprueba que los ejemplos funcionan en una carpeta nueva.
3. Describe el problema o la propuesta en una Issue, sin datos privados.
4. Trabaja en tu fork/rama y envía una pull request con un alcance concreto.

No necesitas ejecutar campañas largas para corregir documentación. No cambies
presupuestos o criterios después de ver un fallo para hacerlo desaparecer.
Conserva negativos e identifica qué versión se probó.

## Construir y comprobar el paquete

Desde la raíz, con el entorno de desarrollo activo:

```console
python -m pip install build
python -m build
python -m venv .venv-check
```

La compilación deja el wheel y la fuente en `dist`. Instala el wheel en el
entorno de comprobación, NO en el de desarrollo. Sustituye `RUTA_WHEEL` por el
nombre real del archivo `dist/protoagent_framework-...whl`:

Windows PowerShell:

```powershell
.\.venv-check\Scripts\python.exe -m pip install "RUTA_WHEEL[motor]"
.\.venv-check\Scripts\python.exe -I tools/release_gate.py --wheel RUTA_WHEEL --output ./reporte-completo
```

Linux:

```console
.venv-check/bin/python -m pip install "RUTA_WHEEL[motor]"
.venv-check/bin/python -I tools/release_gate.py --wheel RUTA_WHEEL --output ./reporte-completo
```

Para el perfil básico, crea otro entorno sin `[motor]` y añade `--profile base`
al gate. Usa un directorio nuevo para cada reporte. Los logs de éxito y fallo
se conservan allí; revisa `result.json` y los archivos `.stderr`/`.stdout`.

El gate se ejecuta secuencialmente. No necesita LLM, API key, Docker ni datos
reales. La instalación de dependencias sí puede acceder a Internet. GitHub
Actions automatiza ambos perfiles en Windows y Ubuntu.

## Qué debe explicar una contribución

- Objetivo, cambio de comportamiento y compatibilidad.
- Prueba reproducible y al menos un caso negativo de autoridad cuando aplique.
- Autoría: qué escribió una persona/Codex/modelo externo y qué decidió el motor.
- Cambios de esquemas, permisos o replay, con nota de recuperación/migración.

No subas claves, bases de misiones, entornos, pesos de modelos ni datasets
privados. Las contribuciones se presentan bajo Apache-2.0 y deben conservar
atribución y avisos de terceros. La licencia no elimina responsabilidades de
seguridad ni convierte un resultado experimental en garantía de producción.
