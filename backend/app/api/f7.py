"""Versioned HTTP API for F7 milestone and change-control workflows."""

# FastAPI's dependency declaration is intentionally expressed in signatures.
# ruff: noqa: B008

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.auth import MANAGEMENT_ROLES, get_current_user, require_roles

from ..db import get_db
from ..models import AcceptanceCriterion, ChangeRequest, ChangeStatus, CriterionStatus, User
from ..services.calculation_engine import DeterministicCalculationEngine
from ..services.calendar import BusinessCalendar
from ..services.f7 import (
    ChangeControlService,
    F7Error,
    StageDefinition,
    TaskUpdate,
)

router = APIRouter(prefix="/api/v1", tags=["F7 - hitos y cambios"])
CurrentUser = Annotated[User, Depends(get_current_user)]
Manager = Annotated[User, Depends(require_roles(*MANAGEMENT_ROLES))]


class F7Input(BaseModel):
    """Reject undocumented fields, especially client-controlled actor IDs."""

    model_config = ConfigDict(extra="forbid")


class StageInput(F7Input):
    name: str = Field(min_length=1, max_length=120)
    sequence: int = Field(ge=1, le=10)
    sla_hours: int | None = Field(default=None, ge=1)


class ChangeRequestInput(F7Input):
    code: str = Field(min_length=1, max_length=50)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=4000)
    change_type: str
    priority: str = "MEDIA"


class TaskUpdateInput(F7Input):
    task_id: str = Field(min_length=1, max_length=80)
    start: date | None = None
    finish: date | None = None
    duration_days: int | None = Field(default=None, ge=0)
    planned_cost: Decimal | None = Field(default=None, ge=0)
    effort_hours: Decimal | None = Field(default=None, ge=0)
    progress_pct: Decimal | None = Field(default=None, ge=0, le=100)

    def domain(self) -> TaskUpdate:
        """Convert validated transport data into a domain proposal."""

        return TaskUpdate(
            self.task_id,
            self.start,
            self.finish,
            self.duration_days,
            self.planned_cost,
            self.effort_hours,
            self.progress_pct,
        )


class ProposalInput(F7Input):
    updates: list[TaskUpdateInput] = Field(default_factory=list)


class TransitionInput(F7Input):
    status: ChangeStatus
    comment: str | None = Field(default=None, max_length=2000)


class EvidenceInput(F7Input):
    file_name: str = Field(min_length=1, max_length=255)
    storage_key: str = Field(min_length=1, max_length=500)
    content_type: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)


class CriterionInput(F7Input):
    external_id: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=1000)
    verification_method: str = Field(min_length=1, max_length=500)
    responsible_id: uuid.UUID | None = None


def _service(session: Session) -> ChangeControlService:
    """Build a request-scoped coordinator using the shared calculation engine."""

    return ChangeControlService(session, DeterministicCalculationEngine(BusinessCalendar()))


def _error(error: F7Error) -> HTTPException:
    """Map domain errors to a stable client-safe response."""

    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))


def _model_data(model: object, fields: tuple[str, ...]) -> dict[str, object]:
    """Extract a small response without exposing ORM internals."""

    return {field: getattr(model, field) for field in fields}


def _audit(
    session: Session,
    actor: User,
    *,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    before_data: dict[str, object] | None = None,
    after_data: dict[str, object] | None = None,
) -> None:
    """Queue an F7 audit event attributed to the authenticated actor."""

    record_audit(
        session,
        user_id=actor.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_data=before_data,
        after_data=after_data,
    )


@router.post("/projects/{project_id}/workflow/stages")
def configure_stages(
    project_id: uuid.UUID,
    stages: list[StageInput],
    session: Session = Depends(get_db),
    actor: Manager = None,
) -> list[dict[str, object]]:
    """Configure up to ten ordered workflow stages and their SLAs."""

    try:
        result = _service(session).configure_stages(
            project_id,
            [StageDefinition(item.name, item.sequence, item.sla_hours) for item in stages],
        )
        _audit(
            session,
            actor,
            action="CONFIGURE_STAGES",
            entity_type="PROJECT",
            entity_id=project_id,
            after_data={"stage_count": len(result)},
        )
        session.commit()
        return [_model_data(stage, ("id", "name", "sequence", "sla_hours", "is_active")) for stage in result]
    except F7Error as error:
        session.rollback()
        raise _error(error) from error


@router.post("/projects/{project_id}/change-requests", status_code=status.HTTP_201_CREATED)
def create_change_request(
    project_id: uuid.UUID,
    payload: ChangeRequestInput,
    session: Session = Depends(get_db),
    actor: CurrentUser = None,
) -> dict[str, object]:
    """Open a change request and snapshot the configured ten-stage workflow."""

    try:
        request = _service(session).create_change_request(
            project_id,
            code=payload.code,
            title=payload.title,
            description=payload.description,
            change_type=payload.change_type,
            priority=payload.priority,
            requester_id=actor.id,
        )
        session.commit()
        return _model_data(
            request,
            ("id", "project_id", "code", "title", "status", "current_stage_id", "created_at"),
        )
    except F7Error as error:
        session.rollback()
        raise _error(error) from error


@router.post("/change-requests/{request_id}/transitions")
def transition_change_request(
    request_id: uuid.UUID,
    payload: TransitionInput,
    session: Session = Depends(get_db),
    actor: Manager = None,
) -> dict[str, object]:
    """Advance, approve, reject or cancel a change request."""

    try:
        request_before = session.get(ChangeRequest, request_id)
        before_status = request_before.status.value if request_before is not None else None
        request = _service(session).transition(
            request_id, payload.status, user_id=actor.id, comment=payload.comment
        )
        _audit(
            session,
            actor,
            action="TRANSITION",
            entity_type="CHANGE_REQUEST",
            entity_id=request.id,
            before_data={"status": before_status},
            after_data={"status": request.status.value, "comment": payload.comment},
        )
        session.commit()
        return _model_data(request, ("id", "status", "current_stage_id", "decided_at", "closed_at"))
    except F7Error as error:
        session.rollback()
        raise _error(error) from error


@router.get("/change-requests/{request_id}/workflow")
def workflow_status(
    request_id: uuid.UUID,
    session: Session = Depends(get_db),
    _: CurrentUser = None,
) -> dict[str, object]:
    """Expose elapsed/SLA state for the active configurable stage."""

    try:
        return _service(session).workflow_status(request_id)
    except F7Error as error:
        raise _error(error) from error


@router.post("/change-requests/{request_id}/impact")
def simulate_impact(
    request_id: uuid.UUID,
    payload: ProposalInput,
    session: Session = Depends(get_db),
    actor: Manager = None,
) -> dict[str, object]:
    """Run an isolated what-if simulation and save its impact record."""

    try:
        result = _service(session).simulate_change(
            request_id, [item.domain() for item in payload.updates]
        )
        _audit(
            session,
            actor,
            action="SIMULATE_IMPACT",
            entity_type="CHANGE_REQUEST",
            entity_id=request_id,
            after_data={
                "delta_schedule_days": result.delta_schedule_days,
                "delta_cost": str(result.delta_cost),
            },
        )
        session.commit()
        return result.as_dict()
    except F7Error as error:
        session.rollback()
        raise _error(error) from error


@router.post("/projects/{project_id}/baselines/{baseline_id}/compare")
def compare_baseline(
    project_id: uuid.UUID,
    baseline_id: uuid.UUID,
    payload: ProposalInput,
    session: Session = Depends(get_db),
    _: Manager = None,
) -> dict[str, object]:
    """Compare a proposal against an immutable baseline snapshot."""

    try:
        comparison = _service(session).compare_baseline(
            project_id, baseline_id, [item.domain() for item in payload.updates]
        )
        return comparison.as_dict()
    except F7Error as error:
        raise _error(error) from error


@router.post("/change-requests/{request_id}/apply")
def apply_change(
    request_id: uuid.UUID,
    payload: ProposalInput,
    session: Session = Depends(get_db),
    actor: Manager = None,
) -> dict[str, object]:
    """Apply an approved request and create immutable baseline vN+1."""

    try:
        baseline = _service(session).apply_change(
            request_id, [item.domain() for item in payload.updates], user_id=actor.id
        )
        session.commit()
        return _model_data(baseline, ("id", "project_id", "version", "status", "approved_at"))
    except F7Error as error:
        session.rollback()
        raise _error(error) from error


@router.post("/milestones/{milestone_id}/criteria", status_code=status.HTTP_201_CREATED)
def add_criterion(
    milestone_id: uuid.UUID,
    payload: CriterionInput,
    session: Session = Depends(get_db),
    actor: Manager = None,
) -> dict[str, object]:
    """Register an acceptance criterion for a milestone."""

    try:
        criterion = _service(session).add_criterion(
            milestone_id,
            external_id=payload.external_id,
            description=payload.description,
            verification_method=payload.verification_method,
            responsible_id=payload.responsible_id,
        )
        _audit(
            session,
            actor,
            action="CREATE",
            entity_type="ACCEPTANCE_CRITERION",
            entity_id=criterion.id,
            after_data={"external_id": criterion.external_id},
        )
        session.commit()
        return _model_data(
            criterion,
            ("id", "milestone_id", "external_id", "description", "verification_method", "status"),
        )
    except F7Error as error:
        session.rollback()
        raise _error(error) from error


@router.post("/elements/{element_id}/milestone", status_code=status.HTTP_201_CREATED)
def create_milestone(
    element_id: uuid.UUID,
    session: Session = Depends(get_db),
    actor: Manager = None,
) -> dict[str, object]:
    """Turn a Gantt element into a milestone ready for acceptance criteria."""

    try:
        milestone = _service(session).create_milestone(element_id)
        _audit(
            session,
            actor,
            action="CREATE",
            entity_type="MILESTONE",
            entity_id=element_id,
            after_data={"acceptance_status": milestone.acceptance_status.value},
        )
        session.commit()
        return _model_data(milestone, ("element_id", "acceptance_status"))
    except F7Error as error:
        session.rollback()
        raise _error(error) from error


@router.post("/criteria/{criterion_id}/verify")
def verify_criterion(
    criterion_id: uuid.UUID,
    criterion_status: CriterionStatus,
    session: Session = Depends(get_db),
    actor: Manager = None,
) -> dict[str, object]:
    """Record criterion verification and its evidence-ready audit data."""

    try:
        criterion_before = session.get(AcceptanceCriterion, criterion_id)
        before_status = criterion_before.status.value if criterion_before is not None else None
        criterion = _service(session).verify_criterion(
            criterion_id, criterion_status, verified_by=actor.id
        )
        _audit(
            session,
            actor,
            action="VERIFY",
            entity_type="ACCEPTANCE_CRITERION",
            entity_id=criterion.id,
            before_data={"status": before_status} if before_status is not None else None,
            after_data={"status": criterion.status.value, "verified_by": str(actor.id)},
        )
        session.commit()
        return _model_data(criterion, ("id", "status", "verified_by", "verified_at"))
    except F7Error as error:
        session.rollback()
        raise _error(error) from error


@router.post("/criteria/{criterion_id}/evidences", status_code=status.HTTP_201_CREATED)
def add_criterion_evidence(
    criterion_id: uuid.UUID,
    payload: EvidenceInput,
    session: Session = Depends(get_db),
    actor: Manager = None,
) -> dict[str, object]:
    """Attach a file reference to a criterion."""

    try:
        evidence = _service(session).add_evidence(
            criterion_id=criterion_id,
            file_name=payload.file_name,
            storage_key=payload.storage_key,
            content_type=payload.content_type,
            size_bytes=payload.size_bytes,
            uploaded_by=actor.id,
        )
        session.commit()
        return _model_data(evidence, ("id", "criterion_id", "file_name", "storage_key", "uploaded_at"))
    except F7Error as error:
        session.rollback()
        raise _error(error) from error


@router.post("/change-requests/{request_id}/evidences", status_code=status.HTTP_201_CREATED)
def add_change_evidence(
    request_id: uuid.UUID,
    payload: EvidenceInput,
    session: Session = Depends(get_db),
    actor: Manager = None,
) -> dict[str, object]:
    """Attach a file reference to a change request."""

    try:
        evidence = _service(session).add_evidence(
            change_request_id=request_id,
            file_name=payload.file_name,
            storage_key=payload.storage_key,
            content_type=payload.content_type,
            size_bytes=payload.size_bytes,
            uploaded_by=actor.id,
        )
        session.commit()
        return _model_data(evidence, ("id", "change_request_id", "file_name", "storage_key", "uploaded_at"))
    except F7Error as error:
        session.rollback()
        raise _error(error) from error
