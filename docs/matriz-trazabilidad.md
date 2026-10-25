# F18 — Matriz de trazabilidad

Esta matriz conecta el requisito verificable con la tarea del plan, la evidencia
de prueba y el indicador de la rúbrica. Los nombres de tests son rutas reales del
repositorio; cuando una prueba todavía no existe se marca explícitamente como
pendiente, no como evidencia cumplida.

| Requisito | Tarea / fase | Test o evidencia | Indicador |
|---|---|---|---|
| Persistir proyecto, jerarquía, dependencias, recursos, hitos, KPI y cambios con integridad | F1 — modelo y migraciones | `backend/tests/test_f14_integrity.py`, `docs/modelo-datos.md` | Ind.1 |
| Importar XLSX/CSV, validar antes de guardar y rechazar errores/ciclos | F2 — importador y seeds | `backend/tests/test_importer_f2.py`, `backend/tests/test_seed_checklist.py`, `docs/importacion-carta-gantt.md` | Ind.1, Ind.4, Ind.8 |
| Mantener etapas → actividades → subactividades dentro de la Carta Gantt, con consolidación | F5 — Gantt y actividades | `backend/tests/test_calculation_engine.py::test_consolidation_and_costs`, `backend/tests/test_engine_edge_cases.py::test_consolidation_rolls_up_cost_actuals_and_hour_weights` | Ind.2, Ind.4 |
| Calcular calendario, duración, holgura, ruta crítica y propagar cambios | F3 — motor de programación y costos | `backend/tests/test_calculation_engine.py`, `backend/tests/test_engine_edge_cases.py` | Ind.3, Ind.4, Ind.8 |
| Soportar FS, SS, FF y SF, con desfases y rechazo de ciclos | F3 — dependencias | `backend/tests/test_calculation_engine.py`, `backend/tests/test_engine_edge_cases.py` | Ind.4 |
| Calcular costos plan/reales, EVM y sobreasignación | F3/F6 — costos y recursos | `backend/tests/test_calculation_engine.py`, `backend/tests/test_engine_edge_cases.py` | Ind.3, Ind.8 |
| Exponer Gantt, importación y recálculo mediante API persistente | F4 — API | `backend/tests/test_api_contracts.py`, `backend/tests/test_health.py` | Ind.4, Ind.8 |
| Administrar KPI configurables con parser seguro y autorización | F8 — KPI | `backend/tests/test_f15_kpi_security.py` | Ind.5 |
| Gestionar roles, auditoría y permisos de cambios | F11 — roles y auditoría | `backend/tests/test_f7_rbac.py`, `backend/tests/test_f14_integrity.py` | Ind.6, Ind.8 |
| Verificar el caso mínimo: 4 etapas, 12 actividades, 20 subactividades, 4 dependencias, 5 profesionales, 4 recursos, 6 hitos, 8+12 KPI, 5 cambios y 2 tableros | F13 — verificación | `backend/tests/test_seed_checklist.py`, `docs/f9-seeds-checklist.md` | Ind.5, Ind.6, Ind.7, Ind.8 |
| Demostrar cambio de duración, recurso y solicitud aprobada, observando propagación | F13/F18 — demo y trazabilidad | `docs/f9-guion-demo.md`, `docs/f18-guion-trazabilidad.md` (ejecución manual) | Ind.3–Ind.8 |
| Entregar documentación, manual, ADR y trazabilidad sin modificar `insumos/` | F18 — documentación | Este documento, `docs/manual-usuario.md`, `docs/adr/ADR-007-gantt-dependencias.md`, `git diff -- insumos` | Ind.8 |
| Exponer dashboard, snapshots KPI y líneas base persistentes para la UI | F19 — contratos de lectura | `backend/tests/test_f21_contracts.py`, endpoints `dashboard`, `kpis/snapshots` y `baselines` | Ind.5, Ind.7, Ind.8 |
| Consumir contratos persistentes desde la UI y mostrar jerarquía, dependencias, línea base y proyección | F20 — integración UI | `frontend/src/api.ts`, `frontend/src/F5Views.tsx`, `frontend/src/App.tsx`, revisión manual F18 | Ind.2–Ind.8 |
| Publicar y ejecutar what-if, comparación y aplicación transaccional sin campos de actor controlados por cliente | F21 — contratos F7 | `backend/tests/test_f21_contracts.py`, endpoints `/impact`, `/compare` y `/apply` | Ind.6–Ind.8 |

## Lectura de cobertura

- **Cubiertos por pruebas automatizadas:** motor, casos límite, importación,
  contratos API, salud, checklist, integridad, RBAC y seguridad KPI.
- **Cubiertos por evidencia manual:** recorrido visual del Gantt, filtros,
  paneles, actualización de tableros y los tres escenarios de demostración.
- **Límites explícitos:** no hay suite E2E browser ni un test que levante
  Docker completo; la matriz no los presenta como realizados.

## Criterio de consistencia

Un requisito solo se considera trazable cuando tiene tarea, evidencia identificada
y el indicador explícito. La evidencia manual debe registrar fecha, seed, rol,
resultado esperado y resultado observado; los artefactos generados permanecen en
`seeds/` y `insumos/` se trata como fuente de solo lectura.
