"""Atajo compatible para convertir el XLSX original a seeds/."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from trazo_importer.converter import convert_horizonte_to_xlsx  # noqa: E402


def main() -> int:
    source = ROOT / "insumos" / "Caso3_Horizonte_Planificacion_Gantt.xlsx"
    output = ROOT / "seeds" / "Horizonte_Conecta_Carta_Gantt.xlsx"
    workbook = convert_horizonte_to_xlsx(source, output)
    print(f"Convertidas {len(workbook.sheets['Gantt'])} filas Gantt en {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
