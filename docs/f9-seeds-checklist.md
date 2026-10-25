# F9 — Seeds, checklist y carga reproducible

## Artefactos

- **Seed A — Horizonte Conecta:** `seeds/Horizonte_Conecta_Carta_Gantt.xlsx` y
  su representación auditable `seeds/Horizonte_Conecta_Carta_Gantt.json`.
  Proviene de `insumos/Caso3_Horizonte_Planificacion_Gantt.xlsx`; el conversor
  nunca escribe en `insumos/`. Tiene 52 elementos ejecutables (42
  subactividades + 10 hitos), además de sus filas consolidadas.
- **Seed B — Caso de prueba mínimo:**
  `seeds/Seed_B_Caso_Prueba_Minimo.xlsx`,
  `seeds/Seed_B_Caso_Prueba_Minimo.json` y el bundle CSV en
  `seeds/seed_b_caso_prueba_minimo/`. El bundle incluye las siete hojas
  canónicas y los CSV suplementarios de etapas de cambio, cambios, KPI y
  tableros.
- `seeds/build_seed_b.py` reconstruye Seed B sin valores aleatorios.
- `seeds/verificar_f9.py` valida los dos formatos importables y genera
  `seeds/f9_checklist.json`.

## Reset y carga reproducible

Desde la raíz del repositorio:

```text
python seeds/build_seed_b.py
python seeds/verificar_f9.py
```

La primera orden reemplaza únicamente los artefactos de Seed B en `seeds/`.
La segunda hace preview transaccional del XLSX y del bundle CSV (sin guardar
filas si hay errores) y comprueba el Seed A. Para regenerar Seed A desde el
XLSX original:

```text
python scripts/convert_horizonte.py
```

La carga en la aplicación se realiza con el asistente de importación usando
el XLSX de cada seed; el preview debe quedar en verde antes de confirmar y
crear la línea base `v1.0`.

## Checklist automático verificado

| Evidencia | Esperado | Resultado |
|---|---:|---:|
| Etapas Seed B | 4 | 4 |
| Actividades Seed B | 12 | 12 |
| Subactividades Seed B | 20 | 20 |
| Tipos de dependencia | FS, SS, FF, SF | FS, SS, FF, SF |
| Profesionales | 5 | 5 |
| Tipos de recurso | 4 | 4 |
| Hitos con criterio | 6 | 6 |
| Solicitudes de cambio | 5 | 5 |
| KPI proyecto/hitos | 8 | 8 |
| KPI cambio | 12 | 12 |
| Tableros | 2 | 2 |

La fuente de verdad de la ejecución es `seeds/f9_checklist.json`; el comando
termina con código distinto de cero si algún criterio o importación falla.
