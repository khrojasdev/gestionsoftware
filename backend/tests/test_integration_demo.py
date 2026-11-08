"""End-to-end checks of the demo scenarios against a real PostgreSQL database.

They run only when ``TRAZO_DB_TESTS=1`` and ``DATABASE_URL`` points to a
migrated database (CI starts one; locally use docker compose). The demo data
is reloaded at the start, so never point this at a database you care about.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("TRAZO_DB_TESTS") != "1", reason="requires TRAZO_DB_TESTS=1 and PostgreSQL")

PASSWORD = "Trazo2026!"


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("AUTH_SECRET", "integration-secret-integration-secret-123")
    from fastapi.testclient import TestClient

    from app.db import SessionLocal
    from app.demo import load, reset
    from app.main import app

    with SessionLocal() as session:
        reset(session)
        session.commit()
        load(session)
        session.commit()
    return TestClient(app)


def _headers(client, email: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture(scope="module")
def manager(client):
    return _headers(client, "kevin.henriquez@trazo.cl")


@pytest.fixture(scope="module")
def member(client):
    return _headers(client, "diego.lopez@trazo.cl")


@pytest.fixture(scope="module")
def project_id(client, manager) -> str:
    projects = client.get("/api/v1/projects-overview", headers=manager).json()["data"]
    return next(item["id"] for item in projects if item["code"] == "HORIZONTE-CONECTA")


def _data(response) -> Any:
    assert response.status_code < 300, response.text
    return response.json()["data"]


def test_read_models_answer(client, manager, project_id):
    for path in ("gantt/full", "resources/overview", "milestones", "kpis/board", "change-board", "dashboard/project", "dashboard/change", "checklist"):
        assert client.get(f"/api/v1/projects/{project_id}/{path}", headers=manager).status_code == 200, path
    checklist = _data(client.get(f"/api/v1/projects/{project_id}/checklist", headers=manager))
    assert all(item["ok"] for item in checklist["items"])


def test_scenario_1_duration_change_moves_successors(client, manager, project_id):
    result = _data(client.patch(f"/api/v1/projects/{project_id}/elements/A17", headers=manager, json={"duration_days": 27}))
    changed = {row["external_id"]: row for row in result["changes"]}
    assert changed["A17"]["duration_after"] == 27
    assert changed["A17"]["finish_after"] is not None
    assert result["finish_after"]["plan"] > result["finish_before"]["plan"]
    assert len(changed) > 5  # successors and summaries were recalculated too
    gantt = _data(client.get(f"/api/v1/projects/{project_id}/gantt/full", headers=manager))
    assert all(element["finish"] for element in gantt["elements"])


def test_scenario_2_resource_change_detects_overallocation(client, manager, project_id):
    overview = _data(client.get(f"/api/v1/projects/{project_id}/resources/overview", headers=manager))
    task = next(item for item in overview["tasks"] if item["external_id"] == "A18")
    allocation = next(item for item in task["assignments"] if item["resource_external_id"] == "IN1")
    result = _data(
        client.patch(
            f"/api/v1/projects/{project_id}/allocations/{allocation['id']}",
            headers=manager,
            json={"planned_hours": allocation["hours"], "hours_per_day": 16, "effort_driven": True},
        )
    )
    a18 = next(row for row in result["changes"] if row["external_id"] == "A18")
    assert a18["duration_after"] < a18["duration_before"]
    overview = _data(client.get(f"/api/v1/projects/{project_id}/resources/overview", headers=manager))
    assert any(item["resource"] == allocation["resource"] for item in overview["overallocations"])


def test_scenario_3_change_request_creates_new_baseline(client, manager, project_id):
    board = _data(client.get(f"/api/v1/projects/{project_id}/change-board", headers=manager))
    request = next(item for item in board["requests"] if item["code"] == "SC-04")
    before = _data(client.get(f"/api/v1/projects/{project_id}/summary", headers=manager))["baseline_version"]
    _data(client.post(f"/api/v1/change-requests/{request['id']}/advance", headers=manager, json={"comment": "A comité"}))
    _data(client.post(f"/api/v1/change-requests/{request['id']}/decision", headers=manager, json={"approve": True, "comment": "Aprobado"}))
    applied = _data(client.post(f"/api/v1/change-requests/{request['id']}/apply-v2", headers=manager))
    assert applied["baseline_version"] != before
    for _ in range(2):
        _data(client.post(f"/api/v1/change-requests/{request['id']}/advance", headers=manager, json={}))
    detail = _data(client.get(f"/api/v1/change-requests/{request['id']}/detail", headers=manager))
    assert detail["request"]["status"] == "CERRADA"
    assert detail["request"]["applied"] is True
    approvals = [item for item in detail["transitions"] if item["to_status"] == "APROBADA" and item["from_status"] == "ABIERTA"]
    assert len(approvals) == 1


def test_member_permissions(client, member, project_id):
    denied = client.patch(f"/api/v1/projects/{project_id}/elements/A17", headers=member, json={"duration_days": 30})
    assert denied.status_code == 403
    not_mine = client.patch(f"/api/v1/projects/{project_id}/elements/A26", headers=member, json={"progress_pct": 10})
    assert not_mine.status_code == 403
    mine = client.patch(f"/api/v1/projects/{project_id}/elements/A19", headers=member, json={"progress_pct": 25})
    assert mine.status_code == 200, mine.text
    created = client.post(
        f"/api/v1/projects/{project_id}/change-requests-v2",
        headers=member,
        json={"title": "Nueva vista móvil", "description": "Vista resumida para jefes de obra", "change_type": "ALCANCE"},
    )
    assert created.status_code == 201, created.text
    advance = client.post(f"/api/v1/change-requests/{created.json()['data']['id']}/advance", headers=member, json={})
    assert advance.status_code == 403


def test_cycles_and_milestone_criteria_are_rejected(client, manager, project_id):
    cycle = client.post(f"/api/v1/projects/{project_id}/dependencies", headers=manager, json={"predecessor": "A18", "successor": "A17", "type": "FS"})
    assert cycle.status_code == 400
    assert cycle.json()["error"]["code"] == "INVALID_DEPENDENCY"
    milestone = client.patch(f"/api/v1/projects/{project_id}/elements/H05", headers=manager, json={"progress_pct": 100})
    assert milestone.status_code == 409
    assert milestone.json()["error"]["code"] == "MILESTONE_CRITERIA_PENDING"


def test_template_import_creates_full_project(client, manager):
    from pathlib import Path

    template = Path(__file__).resolve().parents[2] / "seeds" / "Carta_Gantt_Plantilla.xlsx"
    with template.open("rb") as handle:
        response = client.post("/api/v1/projects/import", headers=manager, files={"file": ("plantilla.xlsx", handle, "application/octet-stream")})
    created = _data(response)["project"]
    board = _data(client.get(f"/api/v1/projects/{created['id']}/kpis/board", headers=manager))
    assert len(board["kpis"]) == 20
    changes = _data(client.get(f"/api/v1/projects/{created['id']}/change-board", headers=manager))
    assert len(changes["stages"]) == 10
    gantt = _data(client.get(f"/api/v1/projects/{created['id']}/gantt/full", headers=manager))
    assert gantt["elements"] and all(element["finish"] for element in gantt["elements"])


def test_only_admin_can_reset_demo(client, manager):
    assert client.post("/api/v1/admin/demo-reset", headers=manager).status_code == 403
    admin = _headers(client, "admin@trazo.cl")
    restored = _data(client.post("/api/v1/admin/demo-reset", headers=admin))
    assert len(restored["projects"]) == 2
    codes = {item["code"] for item in _data(client.get("/api/v1/projects-overview", headers=admin))}
    assert codes == {"HORIZONTE-CONECTA", "CASO-PRUEBA"}


def test_course_workbook_imports_as_new_project_equivalent_to_demo(client, manager):
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    source = root / "insumos" / "Caso3_Horizonte_Planificacion_Gantt.xlsx"
    if not source.exists():
        source = root / "seeds" / "Horizonte_Conecta_Carta_Gantt.xlsx"
    with source.open("rb") as handle:
        response = client.post(
            "/api/v1/projects/import",
            headers=manager,
            files={"file": ("horizonte.xlsx", handle, "application/octet-stream")},
            data={"codigo": "HORIZONTE-COPIA", "nombre": "Horizonte Conecta (copia)"},
        )
    created = _data(response)["project"]
    assert created["code"] == "HORIZONTE-COPIA"
    projects = {item["code"]: item for item in _data(client.get("/api/v1/projects-overview", headers=manager))}
    original, copy = projects["HORIZONTE-CONECTA"], projects["HORIZONTE-COPIA"]
    assert copy["counts"] == original["counts"]
    assert copy["baseline_version"] == "v1"
    assert copy["bac"] == 212_809_000
    board = _data(client.get(f"/api/v1/projects/{copy['id']}/kpis/board", headers=manager))
    assert len(board["kpis"]) == 20 and all(len(kpi["history"]) >= 1 for kpi in board["kpis"])
    duplicate = client.post(
        "/api/v1/projects/import",
        headers=manager,
        files={"file": ("horizonte.xlsx", source.read_bytes(), "application/octet-stream")},
        data={"codigo": "HORIZONTE-COPIA"},
    )
    assert duplicate.status_code == 409


# These tests run after the demo-reset test, which rebuilds the projects with
# fresh IDs, so the module-scoped project_id fixture is stale here: each test
# resolves the current HORIZONTE-CONECTA id live instead.
def _horizonte(client, manager) -> str:
    projects = client.get("/api/v1/projects-overview", headers=manager).json()["data"]
    return next(item["id"] for item in projects if item["code"] == "HORIZONTE-CONECTA")


def _find_parent(client, manager, project_id, kind: str) -> str:
    gantt = _data(client.get(f"/api/v1/projects/{project_id}/gantt/full", headers=manager))
    return next(element["external_id"] for element in gantt["elements"] if element["kind"] == kind)


def test_create_and_delete_subactivity_recalculates(client, manager):
    project_id = _horizonte(client, manager)
    activity = _find_parent(client, manager, project_id, "ACTIVIDAD")
    before = _data(client.get(f"/api/v1/projects/{project_id}/gantt/full", headers=manager))
    count_before = len(before["elements"])

    created = _data(
        client.post(
            f"/api/v1/projects/{project_id}/elements",
            headers=manager,
            json={"external_id": "QA-NEW-1", "name": "Tarea de prueba CRUD", "element_type": "SUBACTIVIDAD", "parent": activity, "duration_days": 4},
        )
    )
    assert created["external_id"] == "QA-NEW-1"

    after = _data(client.get(f"/api/v1/projects/{project_id}/gantt/full", headers=manager))
    assert len(after["elements"]) == count_before + 1
    new_element = next(element for element in after["elements"] if element["external_id"] == "QA-NEW-1")
    # El recálculo le asignó fechas a partir de la planificación del proyecto.
    assert new_element["start"] and new_element["finish"]
    assert new_element["duration_days"] == 4

    deleted = _data(client.delete(f"/api/v1/projects/{project_id}/elements/QA-NEW-1", headers=manager))
    assert deleted["deleted"] == "QA-NEW-1"
    restored = _data(client.get(f"/api/v1/projects/{project_id}/gantt/full", headers=manager))
    assert len(restored["elements"]) == count_before


def test_create_milestone_creates_milestone_record(client, manager):
    project_id = _horizonte(client, manager)
    activity = _find_parent(client, manager, project_id, "ACTIVIDAD")
    _data(
        client.post(
            f"/api/v1/projects/{project_id}/elements",
            headers=manager,
            json={"external_id": "QA-HITO-1", "name": "Hito de prueba", "element_type": "HITO", "parent": activity},
        )
    )
    milestones = _data(client.get(f"/api/v1/projects/{project_id}/milestones", headers=manager))
    assert any(item["external_id"] == "QA-HITO-1" for item in milestones["milestones"])
    _data(client.delete(f"/api/v1/projects/{project_id}/elements/QA-HITO-1", headers=manager))


def test_delete_element_with_children_is_blocked(client, manager):
    project_id = _horizonte(client, manager)
    stage = _find_parent(client, manager, project_id, "ETAPA")
    response = client.delete(f"/api/v1/projects/{project_id}/elements/{stage}", headers=manager)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "HAS_CHILDREN"


def test_duplicate_external_id_is_rejected(client, manager):
    project_id = _horizonte(client, manager)
    activity = _find_parent(client, manager, project_id, "ACTIVIDAD")
    existing = _find_parent(client, manager, project_id, "SUBACTIVIDAD")
    response = client.post(
        f"/api/v1/projects/{project_id}/elements",
        headers=manager,
        json={"external_id": existing, "name": "Duplicada", "element_type": "SUBACTIVIDAD", "parent": activity, "duration_days": 2},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


def test_member_cannot_create_or_delete_elements(client, manager, member):
    project_id = _horizonte(client, manager)
    activity = _find_parent(client, manager, project_id, "ACTIVIDAD")
    created = client.post(
        f"/api/v1/projects/{project_id}/elements",
        headers=member,
        json={"external_id": "QA-MEMBER", "name": "No permitido", "element_type": "SUBACTIVIDAD", "parent": activity, "duration_days": 3},
    )
    assert created.status_code == 403


def test_create_and_delete_resource(client, manager):
    project_id = _horizonte(client, manager)
    created = _data(
        client.post(
            f"/api/v1/projects/{project_id}/resources-admin",
            headers=manager,
            json={"external_id": "QA-RES-1", "name": "Recurso de prueba", "resource_type": "HUMANO", "rate": 12000, "role": "QA"},
        )
    )
    assert created["id"]
    deleted = _data(client.delete(f"/api/v1/projects/{project_id}/resources-admin/{created['id']}", headers=manager))
    assert deleted["deleted"] == "QA-RES-1"


def test_delete_assigned_resource_is_blocked(client, manager):
    project_id = _horizonte(client, manager)
    overview = _data(client.get(f"/api/v1/projects/{project_id}/resources/overview", headers=manager))
    assigned = next(resource for resource in overview["resources"] if resource["assignments"])
    response = client.delete(f"/api/v1/projects/{project_id}/resources-admin/{assigned['id']}", headers=manager)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RESOURCE_IN_USE"


def test_kpi_comparator_range_and_rule(client, manager):
    project_id = _horizonte(client, manager)
    board = _data(client.get(f"/api/v1/projects/{project_id}/kpis/board", headers=manager))
    kpi = next(item for item in board["kpis"] if item["category"] == "PROYECTO")
    # Configura un KPI en modo RANGO y verifica que la regla y el estado se calculan con el nuevo operador.
    _data(
        client.put(
            f"/api/v1/projects/{project_id}/kpi-config/{kpi['id']}",
            headers=manager,
            json={"comparator": "RANGE", "green_min": 0.9, "green_max": 1.1, "yellow_min": 0.8, "yellow_max": 1.2},
        )
    )
    updated = _data(client.get(f"/api/v1/projects/{project_id}/kpis/board", headers=manager))
    changed = next(item for item in updated["kpis"] if item["id"] == kpi["id"])
    assert changed["comparator"] == "RANGE"
    assert "entre" in changed["rule"].lower()
    assert changed["status"] in {"VERDE", "AMARILLO", "ROJO", "SIN_DATOS", "INFO"}


def test_kpi_comparator_rejects_inconsistent_thresholds(client, manager):
    project_id = _horizonte(client, manager)
    board = _data(client.get(f"/api/v1/projects/{project_id}/kpis/board", headers=manager))
    kpi = next(item for item in board["kpis"] if item["category"] == "PROYECTO")
    # En modo "mayor o igual" el verde debe ser >= al amarillo.
    response = client.put(
        f"/api/v1/projects/{project_id}/kpi-config/{kpi['id']}",
        headers=manager,
        json={"comparator": "GE", "green_threshold": 0.8, "yellow_threshold": 0.95},
    )
    assert response.status_code == 400
