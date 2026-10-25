# ADR-006: Formato canónico y conversor Horizonte

## Decisión

Trazo usará un libro XLSX canónico con las hojas `Proyecto`, `Calendario`,
`Gantt`, `Recursos`, `Asignaciones`, `Criterios` y `Hitos_Tareas`. La misma
estructura se acepta como un directorio de CSV, un archivo por hoja.

La validación ocurre completamente antes de persistir: fechas, calendario,
jerarquía, dependencias (FS/SS/FF/SF), ciclos, recursos, asignaciones y
criterios. El servicio expone una vista previa y solo confirma cuando no hay
errores.

## Alternativas

- Aceptar directamente las hojas originales de Horizonte: descartada porque
  mezcla instrucciones, EDT y cronograma y no permite una validación estable.
- Persistir fila a fila: descartada porque una importación parcialmente válida
  deja el proyecto inconsistente.
- Usar `openpyxl` como requisito obligatorio: descartada para el núcleo; el
  lector OOXML mínimo permite ejecutar validación en el contenedor de backend
  sin agregar una dependencia de runtime. `openpyxl` puede usarse en tooling.

## Consecuencias

El conversor lee únicamente `Cronograma`, `Planificación` y `Calendario` del
libro original y escribe el resultado en `seeds/`. Nunca escribe dentro de
`insumos/`.
