"""Caso de uso importar/validar con vista previa y todo-o-nada."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .models import CANONICAL_SHEETS, CanonicalWorkbook, ImportResult
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

    def _read(self, source: Path) -> CanonicalWorkbook:
        if not source.exists():
            raise FileNotFoundError(source)
        if source.is_dir() or source.suffix.lower() == ".csv":
            raw = read_csv_bundle(source)
        elif source.suffix.lower() == ".xlsx":
            raw = read_xlsx(source)
        else:
            raise ImportFormatError(f"Formato no soportado: {source.suffix}")
        sheets = rows_to_sheets(raw)
        for sheet in CANONICAL_SHEETS:
            sheets.setdefault(sheet, [])
        return CanonicalWorkbook(sheets)
