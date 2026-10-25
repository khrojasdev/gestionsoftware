"""Checklist automático de la evidencia mínima de F9.

Uso desde la raíz::

    python seeds/verificar_f9.py

La salida ``seeds/f9_checklist.json`` es un reporte reproducible y solo se
escriben artefactos dentro de ``seeds/``.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from trazo_importer.service import ImportService, InMemoryImportStore  # noqa: E402


SEEDS = ROOT / "seeds"
SEED_A = SEEDS / "Horizonte_Conecta_Carta_Gantt.xlsx"
SEED_B = SEEDS / "Seed_B_Caso_Prueba_Minimo.xlsx"
SEED_B_CSV = SEEDS / "seed_b_caso_prueba_minimo"
SEED_B_JSON = SEEDS / "Seed_B_Caso_Prueba_Minimo.json"
REPORT = SEEDS / "f9_checklist.json"


def check_importable(path: Path) -> dict[str, Any]:
    """Validate and commit an XLSX/CSV bundle to the disposable store."""

    store = InMemoryImportStore()
    result = ImportService(store).import_file(path)
    return {
        "path": str(path.relative_to(ROOT)),
        "valid": result.report.valid,
        "errors": len(result.report.errors),
        "warnings": len(result.report.warnings),
        "rows": {sheet: len(rows) for sheet, rows in result.preview.sheets.items()},
        "persisted": store.workbook is not None,
        "baseline_version": store.baseline_version,
    }


def count_check(seed: dict[str, Any]) -> dict[str, Any]:
    """Check every count required by the rubric, including dependency types."""

    gantt_counts = Counter(row["tipo"] for row in seed["Gantt"])
    dependency_types: set[str] = set()
    for row in seed["Gantt"]:
        dependency_types.update(re.findall(r"(?:FS|SS|FF|SF)", str(row.get("predecesoras", ""))))
    resource_types = sorted({row["tipo"] for row in seed["Recursos"]})
    professionals = sum(row["tipo"] == "HUMANO" for row in seed["Recursos"])
    criteria_by_milestone = Counter(row["hito_id"] for row in seed["Criterios"])
    milestone_ids = {row["id"] for row in seed["Gantt"] if row["tipo"] == "HITO"}
    checks = {
        "etapas": gantt_counts["ETAPA"] == 4,
        "actividades": gantt_counts["ACTIVIDAD"] == 12,
        "subactividades": gantt_counts["SUBACTIVIDAD"] == 20,
        "dependencias_fs_ss_ff_sf": dependency_types == {"FS", "SS", "FF", "SF"},
        "profesionales": professionals == 5,
        "tipos_recurso": len(resource_types) == 4,
        "hitos": gantt_counts["HITO"] == 6,
        "criterio_por_hito": milestone_ids == set(criteria_by_milestone) and all(value > 0 for value in criteria_by_milestone.values()),
        "cambios": len(seed["Cambios"]) == 5,
        "kpi_proyecto_hitos": len(seed["KPI_Proyecto_Hitos"]) == 8,
        "kpi_cambio": len(seed["KPI_Cambio"]) == 12,
        "tableros": len(seed["Tableros"]) == 2,
    }
    return {
        "checks": checks,
        "counts": {
            "gantt": dict(gantt_counts),
            "recursos": len(seed["Recursos"]),
            "profesionales": professionals,
            "tipos_recurso": resource_types,
            "criterios": len(seed["Criterios"]),
            "cambios": len(seed["Cambios"]),
            "kpi_proyecto_hitos": len(seed["KPI_Proyecto_Hitos"]),
            "kpi_cambio": len(seed["KPI_Cambio"]),
            "tableros": len(seed["Tableros"]),
            "dependencias": sorted(dependency_types),
        },
        "passed": all(checks.values()),
    }


def run() -> int:
    """Run the checklist and return a process-compatible status code."""

    seed = json.loads(SEED_B_JSON.read_text(encoding="utf-8"))
    report: dict[str, Any] = {
        "checklist": "F9 Seeds mínimo, Horizonte y demo",
        "passed": True,
        "seed_a": check_importable(SEED_A),
        "seed_b_xlsx": check_importable(SEED_B),
        "seed_b_csv": check_importable(SEED_B_CSV),
        "seed_b_counts": count_check(seed),
    }
    report["passed"] = bool(
        report["seed_a"]["valid"]
        and report["seed_b_xlsx"]["valid"]
        and report["seed_b_csv"]["valid"]
        and report["seed_b_counts"]["passed"]
    )
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(run())
