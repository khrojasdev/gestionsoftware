from __future__ import annotations

from app.api.f7 import ProposalInput
from app.main import app


def test_f21_publishes_read_contracts_for_gantt_dashboard_and_baselines() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/projects/{project_id}/gantt" in paths
    assert "/api/v1/projects/{project_id}/dashboard" in paths
    assert "/api/v1/projects/{project_id}/baselines" in paths
    assert "/api/v1/change-requests/{request_id}/impact" in paths
    assert "/api/v1/projects/{project_id}/baselines/{baseline_id}/compare" in paths
    assert "/api/v1/change-requests/{request_id}/apply" in paths


def test_f21_proposal_contract_rejects_client_fields() -> None:
    proposal = ProposalInput.model_validate({"updates": [{"task_id": "A01", "duration_days": 3}]})
    assert proposal.updates[0].task_id == "A01"

    try:
        ProposalInput.model_validate({"updates": [{"task_id": "A01", "actor_id": "spoofed"}]})
    except ValueError:
        pass
    else:
        raise AssertionError("F7 proposals must reject undocumented client-controlled fields")
