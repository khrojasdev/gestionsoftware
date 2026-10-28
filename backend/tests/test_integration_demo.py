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
