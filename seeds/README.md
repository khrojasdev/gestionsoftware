# Seeds

## Seeds F9

```text
python seeds/build_seed_b.py
python seeds/verificar_f9.py
```

`Seed_B_Caso_Prueba_Minimo.xlsx` es el archivo importable de la demo y
`seed_b_caso_prueba_minimo/` es su equivalente CSV por hoja. El checklist
automático queda en `f9_checklist.json`.

## Carta Gantt de demostración (RutaViva)

```text
python seeds/build_demo_rutaviva.py
```

Genera `RutaViva_Carta_Gantt_Demo.xlsx`: un proyecto nuevo y distinto del
seed Horizonte (logística de última milla), pensado para crear un proyecto
desde cero en una demo en vivo. Cubre 4 etapas, 12 actividades, 20
subactividades, los 4 tipos de dependencia (FS, SS, FF, SF), 5 profesionales
+ 3 recursos, 6 hitos con criterios, 5 solicitudes de cambio y 20 KPI. Las
fechas las calcula el mismo motor de la app, así el archivo reproduce su
propio cronograma al importarse. Usa `--out ruta.xlsx` para otra ubicación.

Para una **segunda versión** (otro proyecto en vivo), copia
`build_demo_rutaviva.py` y cambia los datos de `STAGES`, `ACTIVITIES`,
`TASKS`, `MILESTONES`, `PROFESSIONALS`, `CHANGES` y el bloque `project`
(código y nombre). La estructura y el motor se encargan del resto.

Esta carpeta está reservada para plantillas y datos de demostración de Trazo. Los archivos generados deben permanecer aquí y no deben escribirse en `insumos/`.
