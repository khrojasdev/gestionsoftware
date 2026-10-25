# Importación de Carta Gantt (F2)

## Comandos

Desde la raíz del repositorio:

```text
python scripts/generate_trazo_import_assets.py
python scripts/convert_horizonte.py
python -m pytest backend/tests -q
```

El primer comando genera `seeds/Carta_Gantt_Plantilla.xlsx`, sus CSV por hoja
y `seeds/Horizonte_Conecta_Carta_Gantt.xlsx`. El conversor solo lee el libro
de `insumos/`; nunca escribe allí.

## Validación y preview

```python
from pathlib import Path
from trazo_importer.service import ImportService, InMemoryImportStore

service = ImportService(InMemoryImportStore())
preview = service.preview(Path("seeds/Carta_Gantt_Plantilla.xlsx"))
if preview.report.valid:
    result = service.import_file(Path("seeds/Carta_Gantt_Plantilla.xlsx"))
```

`ValidationReport` localiza cada error por hoja, fila, columna y código. La
confirmación es todo-o-nada y crea la línea base `v1.0`; las advertencias no
bloquean (por ejemplo, tareas sin recurso o sobreasignación).
