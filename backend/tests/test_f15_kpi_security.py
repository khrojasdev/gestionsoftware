from __future__ import annotations

from pathlib import Path

import pytest

from app.api.errors import ApiError
from app.api.routes import _formula_value, _import_source
from app.config import Settings
from app.services.f7 import DEFAULT_CHANGE_STAGES
from app.services.kpi import KpiFormulaError, evaluate_formula


def test_kpi_parser_supports_catalogue_functions_without_code_execution() -> None:
    values = {"EV": 50, "AC": 100, "BAC": 120}

    assert _formula_value("SUM(EV, AC) / 2", values) == 75
    assert _formula_value("IF(EV < AC, EV, BAC)", values) == 50

    with pytest.raises(ApiError) as error:
        _formula_value("__import__('os').system('whoami')", values)
    assert error.value.code == "INVALID_KPI_FORMULA"


def test_kpi_parser_rejects_variables_outside_catalogue() -> None:
    with pytest.raises(KpiFormulaError, match="no registrada"):
        evaluate_formula("UNKNOWN + 1", {"EV": 50})


def test_import_source_is_confined_to_seeds() -> None:
    with pytest.raises(ApiError) as error:
        _import_source(str(Path.cwd().parent / "README.md"))
    assert error.value.code == "INVALID_IMPORT_SOURCE"


def test_default_change_workflow_has_exactly_ten_prd_stages() -> None:
    assert len(DEFAULT_CHANGE_STAGES) == 10
    assert [stage.sequence for stage in DEFAULT_CHANGE_STAGES] == list(range(1, 11))
    assert DEFAULT_CHANGE_STAGES[-1].name == "Cierre y línea base"


def test_production_requires_explicit_long_auth_secret() -> None:
    with pytest.raises(ValueError, match="AUTH_SECRET"):
        Settings(app_env="production", auth_secret=None)
    settings = Settings(app_env="production", auth_secret="x" * 32)
    assert settings.auth_secret == "x" * 32
