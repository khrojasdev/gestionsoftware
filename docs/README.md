# Documentación técnica

La documentación de arquitectura se organiza en `docs/adr/`; la funcional,
operativa y de evidencia se mantiene separada por concepto.

## Estructura inicial

- `adr/`: decisiones técnicas versionadas.
- `matriz-trazabilidad.md`: requisito → tarea → test → indicador Ind.1–8.
- `manual-usuario.md`: operación por flujo y límites conocidos.
- `f18-guion-trazabilidad.md`: recorrido manual de F18 y evidencia esperada.
- `f9-guion-demo.md` y `f9-seeds-checklist.md`: preparación y demostración del caso.
- `f19-f21-api-ui.md`: referencia de contratos persistentes, límites y operación final.
- `../backend/`: API FastAPI y pruebas.
- `../frontend/`: aplicación React/Vite.
- `../seeds/`: datos y plantillas generadas; nunca se escriben en `insumos/`.

La documentación final corresponde al commit `cde9a0f3fb30286dd36591c2e0f91f8053534f92`.
F19–F21 no agregan una suite E2E: las pruebas automatizadas cubren contratos y
servicios, y el flujo visual se verifica con los guiones manuales.
