"""Genera la plantilla y convierte el seed de Horizonte.

Uso desde la raíz del repositorio (Windows y Unix):
    python scripts/generate_trazo_import_assets.py
    python scripts/generate_trazo_import_assets.py --template-only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from trazo_importer.converter import convert_horizonte_to_xlsx  # noqa: E402
from trazo_importer.template import create_template  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera assets de importación de Trazo")
    parser.add_argument("--template-only", action="store_true", help="No convertir el libro de Horizonte")
    args = parser.parse_args()
    seeds = ROOT / "seeds"
    create_template(seeds / "Carta_Gantt_Plantilla.xlsx", seeds / "plantilla_csv")
    if not args.template_only:
        source = ROOT / "insumos" / "Caso3_Horizonte_Planificacion_Gantt.xlsx"
        workbook = convert_horizonte_to_xlsx(source, seeds / "Horizonte_Conecta_Carta_Gantt.xlsx")
        (seeds / "Horizonte_Conecta_Carta_Gantt.json").write_text(
            json.dumps(workbook.sheets, default=str, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Horizonte convertido: {len(workbook.sheets['Gantt'])} filas Gantt")
    print(f"Plantilla creada: {seeds / 'Carta_Gantt_Plantilla.xlsx'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
