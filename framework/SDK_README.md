# ProtoAgent Framework — guía vigente v0.1 experimental

Candidata0.1.0rc3,Apache-2.0. Guía canónica distribuible:
[distribution/README.md](distribution/README.md), [API](distribution/API.md),
[seguridad](distribution/SECURITY.md), [recuperación](distribution/RECOVERY.md).

Instalar el wheel final en CPython3.12,fuera del checkout; extra[motor] para
sesiones/motor/biblioteca. Sin sys.path privado, sin LLM obligatorio ni daemon
automático. Contratos, permisos actuales y verificador gobiernan los efectos.

Calificación de la candidata se publica en el informe de release con hash;
esta guía por sí sola no afirma éxito. Versiones dev12/dev21/dev26 conservan
sus resultados y negativos. La guía anterior, con notas por versión, permanece
en SDK_README_LEGACY_20261013.md como archivo, no instrucciones vigentes.

Generadores finitos/multifichero y transporte externo son opt-in experimental.
No Python libre, plugins hostiles en proceso, seguridad universal, producción
ni F8 integral. Publicar la distribución requiere autorización específica.
