# F9 — Guion de demostración

## Preparación

1. Ejecutar `python seeds/build_seed_b.py` y
   `python seeds/verificar_f9.py`.
2. Importar `seeds/Seed_B_Caso_Prueba_Minimo.xlsx` y confirmar la línea base
   `v1.0`.
3. Abrir el tablero **Tablero del proyecto** y dejar visible Gantt, costos,
   KPI y la línea base.

## Escenario 1 — Cambiar duración

1. Abrir `A02` (**Trabajo demostrable 02**) y cambiar su duración de 4 a 6
   días hábiles.
2. Guardar el cambio y mostrar el recálculo de sus sucesoras y de `H01`.
3. Verificar la nueva fecha en Gantt, la variación de plazo en `SV`/`SPI` y
   el cambio de costo planificado en el tablero.

## Escenario 2 — Modificar un recurso

1. En la vista de recursos abrir `A05` y reemplazar `R001` por `R003`.
2. Confirmar la nueva asignación y mostrar el cambio de tarifa/costo de la
   subactividad, actividad y etapa consolidada.
3. Mostrar la matriz de carga y la actualización de `CPI`/`CV` en el tablero
   del proyecto.

## Escenario 3 — Aprobar un cambio

1. Abrir el panel F7 de **Gestión de cambios**, seleccionar una solicitud
   autorizada y mostrar la trazabilidad de sus etapas.
2. Seleccionar `CR-002` (agregar tablet), si está presente en el seed, revisar
   el impacto simulado y comparar con la línea base vigente.
3. Ejecutar **Aplicar cambio** después de la transición autorizada. La aplicación debe crear la nueva línea
   base, registrar la transición, actualizar costo/contingencia y recalcular
   Gantt, KPI y **Tablero de gestión del cambio**.
4. Cerrar mostrando el contador de solicitudes, la tasa de aprobación, el
   consumo de contingencia y el historial de auditoría.

## Evidencia a capturar

- Antes y después de la fecha de `A02` y del hito `H01`.
- Antes y después de la asignación de `A05`, con tarifa y carga.
- Impacto y transición de `CR-002`, más la línea base posterior a la
  aprobación.
- `seeds/f9_checklist.json` en estado `"passed": true`.
