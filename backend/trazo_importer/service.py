"""Caso de uso importar/validar con vista previa y todo-o-nada."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .converter import convert_horizonte, is_horizonte_workbook
from .models import CANONICAL_COLUMNS, CANONICAL_SHEETS, SUPPLEMENTAL_SHEETS, CanonicalWorkbook, ImportResult
from .spreadsheet import read_csv_bundle, read_xlsx, rows_to_sheets
from .validation import validate_workbook


class ImportFormatError(ValueError):
    """La fuente no tiene una extensión o estructura legible."""


class ImportStore(Protocol):
    """Puerto de persistencia que debe aplicar un libro en una transacción."""

    def commit_import(self, workbook: CanonicalWorkbook) -> int:
        """Persiste el libro completo y devuelve filas afectadas."""


class InMemoryImportStore:
    """Repositorio transaccional pequeño para tests y vista previa local."""

    def __init__(self) -> None:
        self.workbook: CanonicalWorkbook | None = None
        self.baseline_version: str | None = None

    def commit_import(self, workbook: CanonicalWorkbook) -> int:
        candidate = workbook.copy()
        changed_rows = sum(len(rows) for rows in candidate.sheets.values())
        self.workbook = candidate
        previous = int(self.baseline_version.removeprefix("v").split(".", 1)[0]) if self.baseline_version else 0
        self.baseline_version = f"v{previous + 1}.0"
        return changed_rows


class ImportService:
    """Orquesta lectura, validación y confirmación explícita de una importación."""

    def __init__(self, store: ImportStore | None = None) -> None:
        self._store = store

    def preview(self, source: Path) -> ImportResult:
        workbook = self._read(source)
        report = validate_workbook(workbook)
        baseline = "1.0" if report.valid else None
        return ImportResult(False, workbook, report, baseline_version=baseline)

    def import_file(self, source: Path) -> ImportResult:
        """Importa solo cuando no hay errores; los warnings no bloquean."""

        result = self.preview(source)
        if not result.report.valid or self._store is None:
            return result
        changed_rows = self._store.commit_import(result.preview)
        version = getattr(self._store, "baseline_version", None) or "v1.0"
        return ImportResult(True, result.preview, result.report, changed_rows, version)

    def inspect(self, source: Path) -> dict[str, object]:
        """Describe detected format and the columns found in each sheet."""

        raw = self._raw(source)
        if source.suffix.lower() == ".xlsx" and is_horizonte_workbook(raw):
            converted = convert_horizonte(source)
            return {
                "format": "HORIZONTE",
                "label": "Libro de planificación del curso (Cronograma / Planificación / Calendario)",
                "source_sheets": sorted(raw),
                "sheets": [
                    {
                        "name": name,
                        "rows": len(rows),
                        "found": list(CANONICAL_COLUMNS.get(name, tuple(rows[0].keys()) if rows else ())),
                        "expected": list(CANONICAL_COLUMNS.get(name, ())),
                        "missing": [],
                        "converted": True,
                    }
                    for name, rows in converted.sheets.items()
                ],
            }
        sheets = []
        for name in (*CANONICAL_SHEETS, *SUPPLEMENTAL_SHEETS):
            if name not in raw:
                if name in CANONICAL_SHEETS:
                    sheets.append({"name": name, "rows": 0, "found": [], "expected": list(CANONICAL_COLUMNS[name]), "missing": list(CANONICAL_COLUMNS[name]), "converted": False})
                continue
            rows = raw[name]
            headers = [str(value).strip() for value in rows[0]] if rows else []
            expected = list(CANONICAL_COLUMNS.get(name, headers))
            sheets.append(
                {
                    "name": name,
                    "rows": max(0, len(rows) - 1),
                    "found": [header for header in headers if header],
                    "expected": expected,
                    "missing": [column for column in expected if column not in headers],
                    "converted": False,
                }
            )
        return {"format": "PLANTILLA", "label": "Plantilla Carta Gantt de Trazo", "source_sheets": sorted(raw), "sheets": sheets}

    def _raw(self, source: Path) -> dict:
        if not source.exists():
            raise FileNotFoundError(source)
        if source.is_dir() or source.suffix.lower() == ".csv":
            return read_csv_bundle(source)
        if source.suffix.lower() == ".xlsx":
            return read_xlsx(source)
        raise ImportFormatError(f"Formato no soportado: {source.suffix}")

    def _read(self, source: Path) -> CanonicalWorkbook:
        raw = self._raw(source)
        if source.suffix.lower() == ".xlsx" and is_horizonte_workbook(raw):
            return convert_horizonte(source)
        sheets = rows_to_sheets(raw)
        for sheet in CANONICAL_SHEETS:
            sheets.setdefault(sheet, [])
        return CanonicalWorkbook(sheets)
