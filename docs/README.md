# Documentación técnica

La documentación de arquitectura se organiza en `docs/adr/`; la funcional,
operativa y de evidencia se mantiene separada por concepto.

## Estructura inicial

- `adr/`: decisiones técnicas versionadas.
- `matriz-trazabilidad.md`: requisito → tarea → test → indicador Ind.1–8.
- `manual-usuario.md`: operación por flujo y límites conocidos.
- `f18-guion-trazabilidad.md`: recorrido manual de F18 y evidencia esperada.
- `f9-guion-demo.md` y `f9-seeds-checklist.md`: preparación y demostración del caso.
- `../backend/`: API FastAPI y pruebas.
- `../frontend/`: aplicación React/Vite.
- `../seeds/`: datos y plantillas generadas; nunca se escriben en `insumos/`.
