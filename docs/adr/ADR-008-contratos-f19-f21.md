# ADR-008: contratos persistentes para F19–F21

- **Estado:** aceptado
- **Fecha:** 2026-10-25
- **Tarea:** F19–F21 — integración final de lectura, UI y cambio

## Contexto

La interfaz final debía dejar de depender de datos simulados y permitir que una
propuesta de cambio se inspeccionara y aplicara sin confiar en campos enviados
por el navegador.

## Decisión

- FastAPI expone dashboard, snapshots KPI, baselines y contratos F7 de impacto,
  comparación y aplicación.
- React consume esos contratos y carga importaciones como bytes multipart, no
  como rutas del sistema de archivos del cliente.
- El backend conserva la autoridad sobre actor, permisos, cálculo, auditoría y
  transacción; aplicar un cambio genera una nueva línea base.
- Docker sigue siendo entorno local reproducible. E2E browser y Docker-in-test
  quedan fuera del alcance de esta entrega.

## Consecuencias

**Positivas:** la UI refleja el estado persistido, los resultados son
reproducibles y se reduce la superficie de suplantación del actor.

**Límites:** la demo visual requiere servicios levantados y los escenarios F9/F18
siguen siendo evidencia manual; no se presentan como pruebas E2E automatizadas.
