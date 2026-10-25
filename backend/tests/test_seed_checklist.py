from __future__ import annotations

import json
from pathlib import Path

from seeds.verificar_f9 import SEED_A, SEED_B, SEED_B_CSV, count_check, check_importable


ROOT = Path(__file__).resolve().parents[2]


def test_seed_a_and_seed_b_are_importable_without_touching_insumos() -> None:
    source = ROOT / "insumos" / "Caso3_Horizonte_Planificacion_Gantt.xlsx"
    before = source.read_bytes()

    seed_a = check_importable(SEED_A)
    seed_b_xlsx = check_importable(SEED_B)
    seed_b_csv = check_importable(SEED_B_CSV)

    assert seed_a["valid"] is True
    assert seed_b_xlsx["valid"] is True
    assert seed_b_csv["valid"] is True
    assert source.read_bytes() == before


def test_seed_b_counts_cover_required_demo_data() -> None:
    seed = json.loads((ROOT / "seeds" / "Seed_B_Caso_Prueba_Minimo.json").read_text(encoding="utf-8"))
    result = count_check(seed)

    assert result["passed"] is True
    assert result["checks"] == {key: True for key in result["checks"]}
    assert result["counts"]["dependencias"] == ["FF", "FS", "SF", "SS"]
