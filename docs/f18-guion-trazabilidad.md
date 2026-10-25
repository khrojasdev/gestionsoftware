# F18 — Guion manual de trazabilidad

## Preparación

1. Ejecutar los comandos de seeds del [checklist F9](f9-seeds-checklist.md).
2. Importar el XLSX mínimo y registrar la versión de línea base.
3. Guardar fecha, commit, rol, seed y resultado en la hoja de evidencia del
   equipo; no editar archivos de `insumos/`.

## Recorrido

| Paso | Acción | Resultado esperado / indicador |
|---|---|---|
| 1 | Abrir Carta Gantt y plegar una etapa y una actividad | Se conserva etapa → actividad → subactividad; Ind.2 |
| 2 | Seleccionar una tarea con FS, SS, FF y SF en el seed | Se muestra tipo y desfase; Ind.4 |
| 3 | Cambiar duración de `A02` de 4 a 6 días y recalcular | Sucesoras, hito `H01`, costo y KPI muestran antes/después; Ind.3, 4, 5, 7, 8 |
| 4 | Cambiar recurso de `A05` de `R001` a `R003` | Tarifa, carga, costo y KPI se actualizan; Ind.3, 5, 7, 8 |
| 5 | Abrir una solicitud editable (por ejemplo `CR-002` si existe), usar el panel F7 para *What-if*, comparar la línea base vigente y aplicar | Nueva línea base, auditoría, Gantt, costos, KPI y dashboard se actualizan; Ind.6–8 |
| 6 | Intentar una dependencia cíclica | Se informa el ciclo y no se persiste el cambio; Ind.1, 4, 8 |

## Cierre y límites

Comparar los resultados con `seeds/f9_checklist.json` y adjuntar capturas antes
y después. Este guion es evidencia manual: no reemplaza `pytest` ni declara una
prueba E2E/Docker automatizada. Las rutas y comandos completos están en el
README y en `docs/f9-guion-demo.md`.
