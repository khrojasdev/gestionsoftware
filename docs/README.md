# Documentación

## Uso
- [manual-usuario.md](manual-usuario.md): operación de cada pantalla por rol.
- [guion-demo.md](guion-demo.md): recorrido de la demostración con los 3 escenarios.
- [despliegue.md](despliegue.md): Docker, Render, Railway y servidor propio.
- [importacion-carta-gantt.md](importacion-carta-gantt.md): formato de la plantilla.

## Técnica
- [modelo-datos.md](modelo-datos.md): entidades y relaciones.
- [matriz-trazabilidad.md](matriz-trazabilidad.md): requisito → tarea → prueba → indicador.
- [adr/](adr/): decisiones de arquitectura (sin módulo EDT; contratos de cambio).
- Documentos históricos de fases: `f9-*.md`, `f18-*.md`, `f19-f21-*.md`.

Las pruebas automáticas cubren el motor de cálculo, el importador, la API, permisos,
KPI y, con PostgreSQL (`TRAZO_DB_TESTS=1`), los tres escenarios de la demostración.
