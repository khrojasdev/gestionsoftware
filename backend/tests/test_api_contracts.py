from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.api.routes import _formula_value, _import_source
from app.auth import get_current_user
from app.main import app
from app.models import User
from trazo_importer.spreadsheet import write_xlsx
from trazo_importer.template import template_sheets


client = TestClient(app)


def test_protected_api_returns_stable_authentication_error_envelope() -> None:
    response = client.get("/api/v1/projects")

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "AUTHENTICATION_REQUIRED",
            "message": "Autenticación requerida",
            "details": None,
        }
    }


def test_import_source_rejects_insumos_and_non_supported_extensions() -> None:
    forbidden = Path("insumos") / "source.xlsx"

    try:
        _import_source(str(forbidden))
    except Exception as error:
        assert getattr(error, "code", None) == "INVALID_IMPORT_SOURCE"
    else:
        raise AssertionError("The API must not import academic insumos")

    try:
        _import_source("/tmp/source.txt")
    except Exception as error:
        assert getattr(error, "code", None) == "INVALID_IMPORT_SOURCE"
    else:
        raise AssertionError("The API must reject unsupported import extensions")


def test_kpi_formula_allows_arithmetic_and_rejects_code_execution() -> None:
    assert _formula_value("EV / BAC", {"EV": 50, "BAC": 100}) == 0.5

    try:
        _formula_value("__import__('os').system('whoami')", {})
    except Exception as error:
        assert getattr(error, "code", None) == "INVALID_KPI_FORMULA"
    else:
        raise AssertionError("KPI expressions must not execute arbitrary code")


def test_preview_accepts_real_multipart_xlsx_upload() -> None:
    app.dependency_overrides[get_current_user] = lambda: User(
        email="tester@example.com", full_name="Tester", password_hash="unused"
    )
    try:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "template.xlsx"
            write_xlsx(template_sheets(), path)
            response = client.post(
                "/api/v1/projects/import/preview",
                files={"file": ("template.xlsx", path.read_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        assert response.status_code == 200
        assert response.json()["data"]["valid"] is True
    finally:
        app.dependency_overrides.clear()


def test_import_endpoint_does_not_accept_client_paths() -> None:
    app.dependency_overrides[get_current_user] = lambda: User(
        email="tester@example.com", full_name="Tester", password_hash="unused"
    )
    try:
        response = client.post(
            "/api/v1/projects/import/preview",
            json={"source_path": "seeds/Horizonte_Conecta_Carta_Gantt.xlsx"},
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()
