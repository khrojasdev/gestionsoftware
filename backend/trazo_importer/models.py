"""Tipos de dominio del formato canónico de Carta Gantt."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ValidationIssue:
    """Error o advertencia localizada en una hoja de entrada."""

    severity: str
    sheet: str
    row: int | None
    column: str | None
    code: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "sheet": self.sheet,
            "row": self.row,
            "column": self.column,
            "code": self.code,
            "message": self.message,
        }


@dataclass
class ValidationReport:
    """Resultado completo de la validación, apto para vista previa."""

    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors

    def add_error(
        self,
        sheet: str,
        row: int | None,
        column: str | None,
        code: str,
        message: str,
    ) -> None:
        self.errors.append(ValidationIssue("error", sheet, row, column, code, message))

    def add_warning(
        self,
        sheet: str,
        row: int | None,
        column: str | None,
        code: str,
        message: str,
    ) -> None:
        self.warnings.append(ValidationIssue("warning", sheet, row, column, code, message))

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": [item.as_dict() for item in self.errors],
            "warnings": [item.as_dict() for item in self.warnings],
        }


@dataclass
class CanonicalWorkbook:
    """Filas normalizadas del formato canónico.

    Se mantienen como diccionarios para no acoplar el importador al modelo de
    persistencia. Las claves se corresponden exactamente con las columnas de
    cada hoja y las fechas ya están convertidas a ``datetime.date``.
    """

    sheets: dict[str, list[dict[str, Any]]]

    def copy(self) -> CanonicalWorkbook:
        return CanonicalWorkbook(
            {name: [dict(row) for row in rows] for name, rows in self.sheets.items()}
        )

    @property
    def project_code(self) -> str:
        for row in self.sheets.get("Proyecto", []):
            if str(row.get("clave", "")).strip() == "codigo":
                return str(row.get("valor", "")).strip()
        return ""


@dataclass(frozen=True)
class ImportResult:
    """Respuesta de preview/importación."""

    imported: bool
    preview: CanonicalWorkbook
    report: ValidationReport
    changed_rows: int = 0
    baseline_version: str | None = None


CANONICAL_SHEETS: tuple[str, ...] = (
    "Proyecto",
    "Calendario",
    "Gantt",
    "Recursos",
    "Asignaciones",
    "Criterios",
    "Hitos_Tareas",
)

SUPPLEMENTAL_SHEETS: tuple[str, ...] = (
    "Etapas_Cambio",
    "Cambios",
    "KPI_Proyecto_Hitos",
    "KPI_Cambio",
    "Tableros",
)

CANONICAL_COLUMNS: dict[str, tuple[str, ...]] = {
    "Proyecto": ("clave", "valor"),
    "Calendario": ("fecha", "tipo", "recurso_id", "descripcion"),
    "Gantt": (
        "id",
        "tipo",
        "nombre",
        "padre_id",
        "inicio_plan",
        "fin_plan",
        "duracion_dias",
        "predecesoras",
        "avance_pct",
        "inicio_real",
        "fin_real",
        "costo_real",
    ),
    "Recursos": (
        "recurso_id",
        "nombre",
        "tipo",
        "rol",
        "tarifa",
        "unidad",
        "capacidad_h_dia",
    ),
    "Asignaciones": (
        "tarea_id",
        "recurso_id",
        "horas_planificadas",
        "cantidad",
        "h_dia",
        "tarifa_override",
    ),
    "Criterios": (
        "hito_id",
        "criterio_id",
        "descripcion",
        "forma_de_verificacion",
        "responsable",
    ),
    "Hitos_Tareas": ("hito_id", "tarea_id"),
}

DATE_COLUMNS: dict[str, frozenset[str]] = {
    "Calendario": frozenset({"fecha"}),
    "Gantt": frozenset({"inicio_plan", "fin_plan", "inicio_real", "fin_real"}),
}
