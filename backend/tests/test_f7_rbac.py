from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.f7 import ChangeRequestInput, EvidenceInput, TransitionInput, _audit
from app.auth import (
    MANAGEMENT_ROLES,
    ROLE_ADMIN,
    ROLE_MEMBER,
    ROLE_PROJECT_MANAGER,
    require_roles,
)
from app.models import Role, User
from app.main import app


def _user(role_name: str) -> User:
    return User(
        id=uuid4(),
        email=f"{role_name.casefold()}@example.test",
        full_name="Test User",
        password_hash="unused",
        roles=[Role(name=role_name)],
    )


def test_sensitive_f7_endpoint_requires_authentication() -> None:
    response = TestClient(app).post(
        f"/api/v1/projects/{uuid4()}/workflow/stages",
        json=[{"name": "Registro", "sequence": 1}],
    )

    assert response.status_code == 401


@pytest.mark.parametrize("role_name", [ROLE_ADMIN, ROLE_PROJECT_MANAGER])
def test_management_roles_are_allowed_for_sensitive_f7_operations(role_name: str) -> None:
    actor = _user(role_name)
    dependency = require_roles(*MANAGEMENT_ROLES)

    assert dependency(actor) is actor


def test_integrante_is_rejected_from_sensitive_f7_operations() -> None:
    actor = _user(ROLE_MEMBER)
    dependency = require_roles(*MANAGEMENT_ROLES)

    with pytest.raises(HTTPException) as error:
        dependency(actor)

    assert error.value.status_code == 403


@pytest.mark.parametrize(
    ("schema", "field"),
    [
        (ChangeRequestInput, "requester_id"),
        (TransitionInput, "user_id"),
        (EvidenceInput, "uploaded_by"),
    ],
)
def test_f7_rejects_client_controlled_actor_fields(
    schema: type[ChangeRequestInput] | type[TransitionInput] | type[EvidenceInput],
    field: str,
) -> None:
    values: dict[str, object]
    if schema is ChangeRequestInput:
        values = {
            "code": "CR-1",
            "title": "Cambio",
            "description": "Descripción",
            "change_type": "PLAZO",
            "priority": "MEDIA",
        }
    elif schema is TransitionInput:
        values = {"status": "APROBADA"}
    else:
        values = {"file_name": "evidence.txt", "storage_key": "evidence/evidence.txt"}
    values[field] = str(uuid4())

    with pytest.raises(ValidationError):
        schema.model_validate(values)


def test_f7_audit_uses_authenticated_actor(monkeypatch: pytest.MonkeyPatch) -> None:
    actor = _user(ROLE_ADMIN)
    captured: dict[str, object] = {}

    def capture_audit(session: object, **values: object) -> None:
        captured.update(values)

    monkeypatch.setattr("app.api.f7.record_audit", capture_audit)
    _audit(
        object(),
        actor,
        action="VERIFY",
        entity_type="ACCEPTANCE_CRITERION",
        entity_id=UUID("00000000-0000-0000-0000-000000000001"),
    )

    assert captured["user_id"] == actor.id
