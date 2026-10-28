from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from trazo_importer.converter import convert_horizonte
from trazo_importer.models import CanonicalWorkbook
from trazo_importer.service import ImportService, InMemoryImportStore
from trazo_importer.spreadsheet import write_xlsx
from trazo_importer.template import template_sheets
from trazo_importer.validation import validate_workbook


class ImporterF2Tests(unittest.TestCase):
    def test_template_round_trip_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "template.xlsx"
            write_xlsx(template_sheets(), path)
            result = ImportService().preview(path)
        self.assertTrue(result.report.valid, result.report.as_dict())
        self.assertEqual(result.baseline_version, "1.0")

    def test_cycle_is_reported_with_exact_chain(self) -> None:
        sheets = template_sheets()
        gantt = sheets["Gantt"]
        gantt[2]["predecesoras"] = "A02"
        gantt.append(
            {
                "id": "A02",
                "tipo": "SUBACTIVIDAD",
                "nombre": "Segunda tarea",
                "padre_id": "AC1",
                "inicio_plan": "2026-01-06",
                "fin_plan": "2026-01-06",
                "duracion_dias": "1",
                "predecesoras": "A01",
                "avance_pct": "0",
                "inicio_real": "",
                "fin_real": "",
                "costo_real": "",
            }
        )
        report = validate_workbook(CanonicalWorkbook(sheets))
        cycle_errors = [issue for issue in report.errors if issue.code == "DEPENDENCY_CYCLE"]
        self.assertEqual(len(cycle_errors), 1)
        self.assertIn("A01 → A02 → A01", cycle_errors[0].message)

    def test_invalid_import_does_not_replace_existing_store(self) -> None:
        store = InMemoryImportStore()
        valid = template_sheets()
        store.commit_import(CanonicalWorkbook(valid))
        invalid = template_sheets()
        invalid["Gantt"][2]["id"] = ""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.xlsx"
            write_xlsx(invalid, path)
            result = ImportService(store).import_file(path)
        self.assertFalse(result.imported)
        self.assertEqual(store.workbook.sheets["Gantt"][2]["id"], "A01")

    def test_horizonte_converter_keeps_insumo_immutable_and_creates_52_leaf_elements(self) -> None:
        root = Path(__file__).resolve().parents[2]
        source = root / "insumos" / "Caso3_Horizonte_Planificacion_Gantt.xlsx"
        before = source.read_bytes()
        workbook = convert_horizonte(source)
        after = source.read_bytes()
        leaves = [row for row in workbook.sheets["Gantt"] if row["tipo"] in {"SUBACTIVIDAD", "HITO"}]
        self.assertEqual(len(leaves), 52)
        self.assertEqual(before, after)
        milestones = {row["id"] for row in workbook.sheets["Gantt"] if row["tipo"] == "HITO"}
        self.assertEqual({row["hito_id"] for row in workbook.sheets["Criterios"]}, milestones)
        self.assertGreaterEqual(len(workbook.sheets["Criterios"]), 10)
        self.assertTrue({row["tipo"] for row in workbook.sheets["Recursos"]} >= {"HUMANO", "EQUIPAMIENTO", "INFRAESTRUCTURA_LICENCIA", "SERVICIO_EXTERNO"})
        dependencies = ";".join(row["predecesoras"] for row in workbook.sheets["Gantt"])
        self.assertTrue({"SS", "FF", "SF"} <= {dependencies[index : index + 2] for index in range(len(dependencies) - 1)})


if __name__ == "__main__":
    unittest.main()
