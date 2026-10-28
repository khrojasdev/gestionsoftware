"""Read models and commands used by the Trazo web application.

These endpoints aggregate data for each screen (Gantt, resources, milestones,
KPI, change control and dashboards) so the browser does not need to rebuild
calculations.  All numbers come from ``ProjectAnalytics`` and the existing
deterministic engine.
"""

# ruff: noqa: B008

from __future__ import annotations

import mimetypes
import os
import re
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.audit import record_audit
from app.auth import MANAGEMENT_ROLES, ROLE_ADMIN, get_current_user, has_role, require_roles
from app.db import get_db
from app.models import (
    AcceptanceCriterion,
    Assignment,
    AuditLog,
    Baseline,
    ChangeImpact,
    ChangePriority,
    ChangeRequest,
    ChangeRequestStage,
    ChangeStage,
    ChangeStageStatus,
    ChangeStatus,
    ChangeTransition,
    ChangeType,
    CriterionStatus,
    Dashboard,
    Dependency,
    DependencyType,
    Evidence,
    GanttElement,
    GanttElementType,
    Kpi,
    KpiFormulaVersion,
    KpiScope,
    KpiValue,
    ManualMetric,
    Milestone,
    MilestoneTask,
    ProgressRecord,
    Project,
    ProjectStatus,
    Resource,
    ResourceType,
    User,
)
from app.services.analytics import (
    MANUAL_METRICS,
    STATUS_LABELS,
    ElementState,
    ProjectAnalytics,
    json_value,
    kpi_status,
    project_clock,
)
from app.services.calculation_engine import DeterministicCalculationEngine
from app.services.change_flow import ChangeFlow, ChangeFlowError, ensure_stages, simulate_proposal
from app.services.kpi import DEFAULT_KPI_VARIABLES, KpiFormulaError, validate_formula
from app.services.kpi_engine import evaluate, recalculate_kpis, variable_codes
from app.services.persistence import _domain_tasks, project_calendar, recalculate_project, require_project
from app.services.scheduler import ScheduleError

router = APIRouter(prefix="/api/v1", tags=["aplicación web"])
CurrentUser = Annotated[User, Depends(get_current_user)]
Manager = Annotated[User, Depends(require_roles(*MANAGEMENT_ROLES))]
ZERO = Decimal("0")
HUNDRED = Decimal("100")
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", Path(__file__).resolve().parents[2] / "data" / "uploads"))
MAX_UPLOAD = 15 * 1024 * 1024


def ok(data: Any, **meta: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"data": json_value(data)}
    if meta:
        body["meta"] = json_value(meta)
    return body


def _natural(value: str) -> list[Any]:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", value)]


def _user_names(session: Session) -> dict[uuid.UUID, str]:
    return {user.id: user.full_name for user in session.scalars(sa.select(User)).all()}


def _commit_with_kpis(session: Session, project: Project) -> ProjectAnalytics:
    analytics = ProjectAnalytics(session, project)
    recalculate_kpis(session, project, analytics=analytics)
    session.commit()
    return analytics


# =========================================================== projects
def _project_summary(session: Session, project: Project) -> dict[str, Any]:
    has_plan = session.scalar(
        sa.select(sa.func.count(GanttElement.id)).where(GanttElement.project_id == project.id)
    )
    summary: dict[str, Any] = {
        "id": project.id,
        "code": project.code,
        "name": project.name,
        "client": project.client,
        "status": project.status.value,
        "planned_start": project.planned_start,
        "committed_finish": project.committed_finish,
        "cutoff_date": project.cutoff_date,
        "budget": project.budget,
        "contingency_pct": project.contingency_pct,
        "working_hours_per_day": project.working_hours_per_day,
        "responsible_id": project.responsible_id,
        "responsible": session.get(User, project.responsible_id).full_name if project.responsible_id else None,
        "has_plan": bool(has_plan),
    }
    if not has_plan:
        return summary
    analytics = ProjectAnalytics(session, project)
    finish = analytics.project_finish()
    metrics = analytics.metrics()
    counts = defaultdict(int)
    for state in analytics.states.values():
        counts[state.kind] += 1
    baseline = analytics.baseline
    summary.update(
        {
            "progress_real": metrics["AVANCE_REAL"],
            "progress_plan": metrics["AVANCE_PLAN"],
            "bac": metrics["BAC"],
            "ac": metrics["AC"],
            "spi": metrics["SPI"],
            "cpi": metrics["CPI"],
            "baseline_finish": finish["baseline"],
            "forecast_finish": finish["forecast"],
            "start": finish["start"],
            "baseline_version": baseline.version if baseline else None,
            "counts": {
                "stages": counts["ETAPA"],
                "activities": counts["ACTIVIDAD"],
                "subactivities": counts["SUBACTIVIDAD"],
                "milestones": counts["HITO"],
            },
            "open_changes": session.scalar(
                sa.select(sa.func.count(ChangeRequest.id)).where(
                    ChangeRequest.project_id == project.id,
                    ChangeRequest.status.in_([ChangeStatus.OPEN, ChangeStatus.APPROVED]),
                )
            ),
        }
    )
    return summary


@router.get("/projects-overview")
def projects_overview(session: Session = Depends(get_db), _: CurrentUser = None) -> dict[str, Any]:
    projects = session.scalars(sa.select(Project).order_by(Project.created_at)).all()
    return ok([_project_summary(session, project) for project in projects])


@router.get("/projects/{project_id}/summary")
def project_summary(project_id: uuid.UUID, session: Session = Depends(get_db), _: CurrentUser = None) -> dict[str, Any]:
    return ok(_project_summary(session, require_project(session, project_id)))


class ProjectInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    client: str | None = Field(default=None, max_length=200)
    status: ProjectStatus | None = None
    planned_start: date | None = None
    committed_finish: date | None = None
    cutoff_date: date | None = None
    budget: Decimal | None = Field(default=None, ge=0)
    contingency_pct: Decimal | None = Field(default=None, ge=0, le=100)
    working_hours_per_day: Decimal | None = Field(default=None, gt=0)
    responsible_id: uuid.UUID | None = None


@router.post("/projects-admin", status_code=201)
def create_project_admin(payload: ProjectInput, session: Session = Depends(get_db), actor: Manager = None) -> dict[str, Any]:
    if not payload.code or not payload.name:
        raise ApiError("VALIDATION_ERROR", "Código y nombre son obligatorios")
    if session.scalar(sa.select(Project).where(Project.code == payload.code)):
        raise ApiError("CONFLICT", "Ya existe un proyecto con ese código", 409)
    data = payload.model_dump(exclude_unset=True)
    if data.get("status") == ProjectStatus.CLOSED:
        raise ApiError("PROJECT_NOT_READY", "Un proyecto nuevo no puede crearse cerrado", 409)
    project = Project(**data)
    session.add(project)
    session.flush()
    record_audit(session, user_id=actor.id, action="CREATE", entity_type="PROJECT", entity_id=project.id, after_data={"code": project.code})
    session.commit()
    return ok(_project_summary(session, project))


@router.patch("/projects-admin/{project_id}")
def update_project_admin(
    project_id: uuid.UUID, payload: ProjectInput, session: Session = Depends(get_db), actor: Manager = None
) -> dict[str, Any]:
    project = require_project(session, project_id)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("status") == ProjectStatus.CLOSED and project.status != ProjectStatus.CLOSED:
        from app.api.routes import _validate_project_closure

        _validate_project_closure(session, project)
    before = {key: getattr(project, key) for key in changes}
    for key, value in changes.items():
        setattr(project, key, value)
    record_audit(
        session, user_id=actor.id, action="UPDATE", entity_type="PROJECT", entity_id=project.id,
        before_data=json_value(before), after_data=json_value(changes),
    )
    session.flush()
    if {"cutoff_date", "planned_start"} & set(changes) and _has_plan(session, project):
        if "planned_start" in changes:
            recalculate_project(session, project)
        _commit_with_kpis(session, project)
    else:
        session.commit()
    return ok(_project_summary(session, project))


@router.delete("/projects-admin/{project_id}", status_code=204)
def delete_project_admin(
    project_id: uuid.UUID,
    session: Session = Depends(get_db),
    actor: Annotated[User, Depends(require_roles(ROLE_ADMIN))] = None,
) -> Response:
    project = require_project(session, project_id)
    session.execute(sa.text("ALTER TABLE baseline_elements DISABLE TRIGGER trg_baseline_elements_immutable"))
    try:
        _purge_project(session, project)
        record_audit(session, user_id=actor.id, action="DELETE", entity_type="PROJECT", entity_id=project_id, after_data={"code": project.code})
        session.flush()
    finally:
        session.execute(sa.text("ALTER TABLE baseline_elements ENABLE TRIGGER trg_baseline_elements_immutable"))
    session.commit()
    return Response(status_code=204)


@router.post("/admin/demo-reset")
def reset_demo(
    session: Session = Depends(get_db),
    actor: Annotated[User, Depends(require_roles(ROLE_ADMIN))] = None,
) -> dict[str, Any]:
    """Delete every project and reload the demonstration data (admin only)."""

    from app.demo import load, reset

    reset(session)
    session.flush()
    projects = load(session)
    record_audit(session, user_id=actor.id, action="DEMO_RESET", entity_type="PROJECT", entity_id=None, after_data={"projects": [p.code for p in projects.values()]})
    session.commit()
    return ok({"projects": [project.name for project in projects.values()]})


def _purge_project(session: Session, project: Project) -> None:
    project_id = project.id
    element_ids = list(session.scalars(sa.select(GanttElement.id).where(GanttElement.project_id == project_id)).all())
    request_ids = list(session.scalars(sa.select(ChangeRequest.id).where(ChangeRequest.project_id == project_id)).all())
    from app.models import ActualCost, BaselineElement, CalendarEntry, KpiVariable

    if request_ids:
        session.execute(sa.delete(Evidence).where(Evidence.change_request_id.in_(request_ids)))
        session.execute(sa.delete(ChangeImpact).where(ChangeImpact.request_id.in_(request_ids)))
        session.execute(sa.delete(ChangeTransition).where(ChangeTransition.request_id.in_(request_ids)))
        session.execute(sa.delete(ChangeRequestStage).where(ChangeRequestStage.request_id.in_(request_ids)))
        session.execute(sa.delete(ChangeRequest).where(ChangeRequest.id.in_(request_ids)))
    session.execute(sa.delete(ChangeStage).where(ChangeStage.project_id == project_id))
    kpi_ids = list(session.scalars(sa.select(Kpi.id).where(Kpi.project_id == project_id)).all())
    if kpi_ids:
        session.execute(sa.delete(KpiValue).where(KpiValue.kpi_id.in_(kpi_ids)))
        session.execute(sa.delete(KpiFormulaVersion).where(KpiFormulaVersion.kpi_id.in_(kpi_ids)))
        session.execute(sa.delete(Kpi).where(Kpi.id.in_(kpi_ids)))
    session.execute(sa.delete(KpiVariable).where(KpiVariable.project_id == project_id))
    session.execute(sa.delete(Dashboard).where(Dashboard.project_id == project_id))
    session.execute(sa.delete(ManualMetric).where(ManualMetric.project_id == project_id))
    if element_ids:
        criteria = list(session.scalars(sa.select(AcceptanceCriterion.id).where(AcceptanceCriterion.milestone_id.in_(element_ids))).all())
        if criteria:
            session.execute(sa.delete(Evidence).where(Evidence.criterion_id.in_(criteria)))
            session.execute(sa.delete(AcceptanceCriterion).where(AcceptanceCriterion.id.in_(criteria)))
        session.execute(sa.delete(MilestoneTask).where(sa.or_(MilestoneTask.milestone_id.in_(element_ids), MilestoneTask.element_id.in_(element_ids))))
        session.execute(sa.delete(Milestone).where(Milestone.element_id.in_(element_ids)))
        session.execute(sa.delete(ProgressRecord).where(ProgressRecord.element_id.in_(element_ids)))
        session.execute(sa.delete(ActualCost).where(ActualCost.element_id.in_(element_ids)))
        session.execute(sa.delete(Assignment).where(Assignment.project_id == project_id))
        session.execute(sa.delete(Dependency).where(Dependency.project_id == project_id))
    baseline_ids = list(session.scalars(sa.select(Baseline.id).where(Baseline.project_id == project_id)).all())
    if baseline_ids:
        session.execute(sa.delete(BaselineElement).where(BaselineElement.baseline_id.in_(baseline_ids)))
        session.execute(sa.text("ALTER TABLE baselines DISABLE TRIGGER trg_baselines_immutable_plan"))
        session.execute(sa.delete(Baseline).where(Baseline.id.in_(baseline_ids)))
        session.execute(sa.text("ALTER TABLE baselines ENABLE TRIGGER trg_baselines_immutable_plan"))
    if element_ids:
        session.execute(sa.update(GanttElement).where(GanttElement.project_id == project_id).values(parent_id=None))
        session.execute(sa.delete(GanttElement).where(GanttElement.project_id == project_id))
    session.execute(sa.delete(CalendarEntry).where(CalendarEntry.project_id == project_id))
    session.execute(sa.delete(Resource).where(Resource.project_id == project_id))
    session.delete(project)


def _has_plan(session: Session, project: Project) -> bool:
    return bool(session.scalar(sa.select(sa.func.count(GanttElement.id)).where(GanttElement.project_id == project.id)))


# ============================================================== gantt
def _element_payload(state: ElementState, level: int, order: int) -> dict[str, Any]:
    return {
        "id": state.id,
        "external_id": state.external_id,
        "kind": state.kind,
        "name": state.name,
        "parent": state.parent_external_id,
        "level": level,
        "order": order,
        "start": state.start,
        "finish": state.finish,
        "duration_days": state.duration_days,
        "baseline_start": state.baseline_start,
        "baseline_finish": state.baseline_finish,
        "baseline_cost": state.baseline_cost,
        "forecast_start": state.forecast_start,
        "forecast_finish": state.forecast_finish,
        "actual_start": state.actual_start,
        "actual_finish": state.actual_finish,
        "progress": state.progress_pct,
        "planned_pct": state.planned_pct * HUNDRED,
        "status": state.status,
        "status_label": STATUS_LABELS.get(state.status, state.status),
        "slip_days": state.slip_days,
        "is_critical": state.is_critical,
        "total_slack": state.total_slack_days,
        "free_slack": state.free_slack_days,
        "planned_cost": state.planned_cost,
        "actual_cost": state.actual_cost,
        "predecessors": state.predecessors,
        "resources": sorted(set(state.resources)),
        "children": len(state.children),
    }


def ordered_states(analytics: ProjectAnalytics) -> list[tuple[ElementState, int]]:
    states = analytics.states
    result: list[tuple[ElementState, int]] = []

    def sort_key(state: ElementState) -> Any:
        if state.is_leaf:
            return (1, state.start or date.max, 0 if state.kind == "SUBACTIVIDAD" else 1, _natural(state.external_id))
        return (0, _natural(state.external_id))

    def visit(state: ElementState, level: int) -> None:
        result.append((state, level))
        children = sorted((states[child] for child in state.children), key=sort_key)
        for child in children:
            visit(child, level + 1)

    roots = sorted((state for state in states.values() if state.parent_external_id is None), key=sort_key)
    for root in roots:
        visit(root, 0)
    return result


@router.get("/projects/{project_id}/gantt/full")
def gantt_full(project_id: uuid.UUID, session: Session = Depends(get_db), _: CurrentUser = None) -> dict[str, Any]:
    project = require_project(session, project_id)
    analytics = ProjectAnalytics(session, project)
    finish = analytics.project_finish()
    elements = [_element_payload(state, level, index) for index, (state, level) in enumerate(ordered_states(analytics))]
    critical_leaves = {state.external_id for state in analytics.leaves() if state.is_critical}
    links = []
    for state in analytics.leaves():
        for item in state.predecessors:
            links.append(
                {
                    "id": item["id"],
                    "from": item["predecessor"],
                    "to": state.external_id,
                    "type": item["type"],
                    "lag_days": item["lag_days"],
                    "critical": item["predecessor"] in critical_leaves and state.external_id in critical_leaves,
                }
            )
    calendar = analytics.calendar
    reserve = (
        calendar.working_days_between(finish["forecast"], project.committed_finish)
        if finish["forecast"] and project.committed_finish
        else None
    )
    slip = calendar.working_days_between(finish["baseline"], finish["forecast"]) if finish["baseline"] and finish["forecast"] else 0
    return ok(
        {
            "project": _project_summary(session, project),
            "cutoff": analytics.cutoff,
            "baseline_version": analytics.baseline.version if analytics.baseline else None,
            "summary": {
                "start": finish["start"],
                "baseline_finish": finish["baseline"],
                "plan_finish": finish["plan"],
                "forecast_finish": finish["forecast"],
                "committed_finish": project.committed_finish,
                "slip_days": slip,
                "reserve_days": reserve,
                "critical_count": len(critical_leaves),
            },
            "holidays": sorted(calendar.holidays),
            "elements": elements,
            "links": links,
        }
    )


class ElementCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=300)
    duration_days: int | None = Field(default=None, ge=0)
    planned_start: date | None = None
    progress_pct: Decimal | None = Field(default=None, ge=0, le=100)
    actual_start: date | None = None
    actual_finish: date | None = None
    actual_cost: Decimal | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=1000)


def _snapshot(session: Session, project_id: uuid.UUID) -> dict[str, tuple[Any, ...]]:
    return {
        element.external_id: (element.planned_start, element.planned_finish, element.duration_days, element.planned_cost)
        for element in session.scalars(sa.select(GanttElement).where(GanttElement.project_id == project_id)).all()
    }


def _diff(before: dict[str, tuple[Any, ...]], after: dict[str, tuple[Any, ...]], names: dict[str, str]) -> list[dict[str, Any]]:
    changes = []
    for key, values in after.items():
        old = before.get(key)
        if old is None or old == values:
            continue
        changes.append(
            {
                "external_id": key,
                "name": names.get(key, key),
                "start_before": old[0],
                "start_after": values[0],
                "finish_before": old[1],
                "finish_after": values[1],
                "duration_before": old[2],
                "duration_after": values[2],
                "cost_before": old[3],
                "cost_after": values[3],
            }
        )
    return sorted(changes, key=lambda item: (item["start_after"] or date.max, _natural(item["external_id"])))


def _require_element(session: Session, project_id: uuid.UUID, element_id: str) -> GanttElement:
    query = sa.select(GanttElement).where(GanttElement.project_id == project_id)
    try:
        query = query.where(GanttElement.id == uuid.UUID(element_id))
    except ValueError:
        query = query.where(GanttElement.external_id == element_id)
    element = session.scalar(query)
    if element is None:
        raise ApiError("NOT_FOUND", "Elemento Gantt no encontrado", 404)
    return element


def _recalculate(session: Session, project: Project) -> None:
    try:
        recalculate_project(session, project)
    except ScheduleError as error:
        session.rollback()
        raise ApiError("INVALID_SCHEDULE", str(error), 400) from error


@router.patch("/projects/{project_id}/elements/{element_id}")
def update_element(
    project_id: uuid.UUID,
    element_id: str,
    payload: ElementCommand,
    session: Session = Depends(get_db),
    actor: CurrentUser = None,
) -> dict[str, Any]:
    project = require_project(session, project_id)
    element = _require_element(session, project_id, element_id)
    data = payload.model_dump(exclude_unset=True)
    schedule_fields = {"name", "duration_days", "planned_start"}
    is_manager = has_role(actor, *MANAGEMENT_ROLES)
    if schedule_fields & set(data) and not is_manager:
        raise ApiError("FORBIDDEN", "Solo Administrador o Jefe de Proyecto modifican la planificación", 403)
    if not is_manager and not _is_assigned(session, element, actor):
        raise ApiError("FORBIDDEN", "Solo puedes registrar avance en tareas asignadas a ti", 403)
    kind = element.element_type.value
    if kind in {"ETAPA", "ACTIVIDAD"} and set(data) - {"name"}:
        raise ApiError("INVALID_HIERARCHY", "Etapas y actividades se consolidan desde sus subactividades")
    if kind == "HITO" and data.get("duration_days") not in (None, 0):
        raise ApiError("INVALID_DURATION", "Un hito siempre tiene duración 0")
    if kind == "HITO" and data.get("progress_pct") is not None and data["progress_pct"] >= HUNDRED:
        criteria = session.scalars(sa.select(AcceptanceCriterion).where(AcceptanceCriterion.milestone_id == element.id)).all()
        if criteria and any(item.status != CriterionStatus.MET for item in criteria):
            raise ApiError(
                "MILESTONE_CRITERIA_PENDING",
                "El hito solo se cumple cuando todos sus criterios de aceptación están cumplidos",
                409,
            )
    if kind == "SUBACTIVIDAD" and data.get("duration_days") == 0:
        raise ApiError("INVALID_DURATION", "La duración de una subactividad debe ser mayor que cero")
    before = _snapshot(session, project_id)
    names = {e.external_id: e.name for e in session.scalars(sa.select(GanttElement).where(GanttElement.project_id == project_id)).all()}
    finish_before = ProjectAnalytics(session, project).project_finish()
    audit_before = {key: getattr(element, key, None) for key in data if key != "notes"}
    if "name" in data:
        element.name = data["name"]
    if "duration_days" in data:
        element.duration_days = data["duration_days"]
        element.effort_hours = None
        element.planned_finish = None
    if "planned_start" in data:
        element.planned_start = data["planned_start"]
        element.planned_finish = None
    progress_fields = {"progress_pct", "actual_start", "actual_finish", "actual_cost"} & set(data)
    if progress_fields:
        progress = data.get("progress_pct", element.progress_pct)
        element.progress_pct = progress
        if "actual_start" in data:
            element.actual_start = data["actual_start"]
        if "actual_finish" in data:
            element.actual_finish = data["actual_finish"]
        if "actual_cost" in data:
            element.actual_cost = data["actual_cost"]
        if progress and progress > 0 and element.actual_start is None:
            element.actual_start = project.cutoff_date or date.today()
        if progress is not None and progress >= HUNDRED and element.actual_finish is None:
            element.actual_finish = project.cutoff_date or date.today()
        if progress is not None and progress < HUNDRED and "actual_finish" not in data:
            element.actual_finish = None
        cutoff_at = datetime.combine(project.cutoff_date or date.today(), datetime.min.time(), tzinfo=UTC)
        record = session.scalar(
            sa.select(ProgressRecord).where(ProgressRecord.element_id == element.id, ProgressRecord.cutoff_at == cutoff_at)
        )
        if record is None:
            record = ProgressRecord(element_id=element.id, cutoff_at=cutoff_at, progress_pct=progress)
            session.add(record)
        record.progress_pct = progress
        record.actual_start = element.actual_start
        record.actual_finish = element.actual_finish
        record.recorded_by = actor.id
        record.notes = data.get("notes")
    record_audit(
        session, user_id=actor.id, action="UPDATE", entity_type="GANTT_ELEMENT", entity_id=element.id,
        before_data=json_value(audit_before), after_data=json_value({k: v for k, v in data.items()}),
    )
    session.flush()
    _recalculate(session, project)
    after = _snapshot(session, project_id)
    analytics = _commit_with_kpis(session, project)
    changes = _diff(before, after, names)
    return ok(
        {
            "element": element.external_id,
            "changes": changes,
            "finish_before": finish_before,
            "finish_after": analytics.project_finish(),
        }
    )


def _is_assigned(session: Session, element: GanttElement, user: User) -> bool:
    return bool(
        session.scalar(
            sa.select(sa.func.count(Assignment.id))
            .join(Resource, Assignment.resource_id == Resource.id)
            .where(Assignment.element_id == element.id, Resource.user_id == user.id)
        )
    )


class DependencyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    predecessor: str = Field(min_length=1, max_length=80)
    successor: str | None = Field(default=None, min_length=1, max_length=80)
    type: DependencyType = DependencyType.FS
    lag_days: int = Field(default=0, ge=-365, le=365)


def _validate_graph(session: Session, project: Project) -> None:
    tasks, _, _ = _domain_tasks(session, project)
    leaves = [task for task in tasks if task.kind in {"SUBACTIVIDAD", "HITO"}]
    try:
        DeterministicCalculationEngine(project_calendar(session, project)).scheduler.validate_graph(leaves)
    except ScheduleError as error:
        raise ApiError("INVALID_DEPENDENCY", f"Precedencia rechazada. {error}", 400) from error


def _dependency_change(session: Session, project: Project, actor: User, mutate: Any) -> dict[str, Any]:
    before = _snapshot(session, project.id)
    names = {e.external_id: e.name for e in session.scalars(sa.select(GanttElement).where(GanttElement.project_id == project.id)).all()}
    finish_before = ProjectAnalytics(session, project).project_finish()
    try:
        mutate()
        session.flush()
        _validate_graph(session, project)
    except ApiError:
        session.rollback()
        raise
    _recalculate(session, project)
    after = _snapshot(session, project.id)
    analytics = _commit_with_kpis(session, project)
    return ok({"changes": _diff(before, after, names), "finish_before": finish_before, "finish_after": analytics.project_finish()})


@router.post("/projects/{project_id}/dependencies", status_code=201)
def add_dependency(project_id: uuid.UUID, payload: DependencyInput, session: Session = Depends(get_db), actor: Manager = None) -> dict[str, Any]:
    project = require_project(session, project_id)
    if not payload.successor:
        raise ApiError("VALIDATION_ERROR", "Debe indicar la sucesora")
    predecessor = _require_element(session, project_id, payload.predecessor)
    successor = _require_element(session, project_id, payload.successor)
    for element in (predecessor, successor):
        if element.element_type.value not in {"SUBACTIVIDAD", "HITO"}:
            raise ApiError("INVALID_DEPENDENCY", "Las precedencias conectan subactividades e hitos")
    if predecessor.id == successor.id:
        raise ApiError("INVALID_DEPENDENCY", "Una tarea no puede depender de sí misma")
    exists = session.scalar(sa.select(Dependency).where(Dependency.predecessor_id == predecessor.id, Dependency.successor_id == successor.id))
    if exists:
        raise ApiError("CONFLICT", "La precedencia ya existe", 409)

    def mutate() -> None:
        session.add(
            Dependency(
                project_id=project_id,
                predecessor_id=predecessor.id,
                successor_id=successor.id,
                dependency_type=payload.type,
                lag_days=payload.lag_days,
            )
        )
        record_audit(
            session, user_id=actor.id, action="CREATE", entity_type="DEPENDENCY", entity_id=successor.id,
            after_data={"predecessor": predecessor.external_id, "successor": successor.external_id, "type": payload.type.value, "lag": payload.lag_days},
        )

    return _dependency_change(session, project, actor, mutate)


@router.patch("/projects/{project_id}/dependencies/{dependency_id}")
def update_dependency(
    project_id: uuid.UUID, dependency_id: uuid.UUID, payload: DependencyInput, session: Session = Depends(get_db), actor: Manager = None
) -> dict[str, Any]:
    project = require_project(session, project_id)
    dependency = session.scalar(sa.select(Dependency).where(Dependency.id == dependency_id, Dependency.project_id == project_id))
    if dependency is None:
        raise ApiError("NOT_FOUND", "Precedencia no encontrada", 404)
    predecessor = _require_element(session, project_id, payload.predecessor)

    def mutate() -> None:
        dependency.predecessor_id = predecessor.id
        dependency.dependency_type = payload.type
        dependency.lag_days = payload.lag_days
        record_audit(
            session, user_id=actor.id, action="UPDATE", entity_type="DEPENDENCY", entity_id=dependency.id,
            after_data={"predecessor": predecessor.external_id, "type": payload.type.value, "lag": payload.lag_days},
        )

    return _dependency_change(session, project, actor, mutate)


@router.delete("/projects/{project_id}/dependencies/{dependency_id}")
def delete_dependency(project_id: uuid.UUID, dependency_id: uuid.UUID, session: Session = Depends(get_db), actor: Manager = None) -> dict[str, Any]:
    project = require_project(session, project_id)
    dependency = session.scalar(sa.select(Dependency).where(Dependency.id == dependency_id, Dependency.project_id == project_id))
    if dependency is None:
        raise ApiError("NOT_FOUND", "Precedencia no encontrada", 404)

    def mutate() -> None:
        record_audit(session, user_id=actor.id, action="DELETE", entity_type="DEPENDENCY", entity_id=dependency.id)
        session.delete(dependency)

    return _dependency_change(session, project, actor, mutate)


# ========================================================== resources
def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


@router.get("/projects/{project_id}/resources/overview")
def resources_overview(project_id: uuid.UUID, session: Session = Depends(get_db), _: CurrentUser = None) -> dict[str, Any]:
    project = require_project(session, project_id)
    analytics = ProjectAnalytics(session, project)
    states_by_id = {state.id: state for state in analytics.states.values()}
    stage_of: dict[str, str] = {}
    for state in analytics.states.values():
        cursor = state
        while cursor.parent_external_id:
            cursor = analytics.states[cursor.parent_external_id]
        stage_of[state.external_id] = cursor.external_id
    user_names = _user_names(session)
    assignments_by_resource: dict[uuid.UUID, list[dict[str, Any]]] = defaultdict(list)
    tasks: dict[str, dict[str, Any]] = {}
    totals_by_type: dict[str, Decimal] = defaultdict(lambda: ZERO)
    totals_by_stage: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for assignment in analytics.assignments:
        resource = analytics.resource_by_id.get(assignment.resource_id)
        state = states_by_id.get(assignment.element_id)
        if resource is None or state is None:
            continue
        human = resource.resource_type == ResourceType.HUMAN
        rate = assignment.rate_override if assignment.rate_override is not None else resource.rate
        amount = assignment.planned_hours if human else assignment.quantity
        cost = (amount or ZERO) * (rate or ZERO)
        row = {
            "id": assignment.id,
            "resource_id": resource.id,
            "resource": resource.name,
            "resource_external_id": resource.external_id,
            "resource_type": resource.resource_type.value,
            "role": resource.role,
            "element_id": state.id,
            "external_id": state.external_id,
            "name": state.name,
            "stage": stage_of.get(state.external_id),
            "hours": assignment.planned_hours if human else None,
            "quantity": None if human else assignment.quantity,
            "unit": resource.unit,
            "hours_per_day": assignment.hours_per_day if human else None,
            "rate": rate,
            "cost": cost,
            "start": state.start,
            "finish": state.finish,
            "duration_days": state.duration_days,
            "progress": state.progress_pct,
            "status": state.status,
        }
        assignments_by_resource[resource.id].append(row)
        task = tasks.setdefault(
            state.external_id,
            {
                "element_id": state.id,
                "external_id": state.external_id,
                "name": state.name,
                "stage": stage_of.get(state.external_id),
                "stage_name": analytics.states[stage_of[state.external_id]].name if state.external_id in stage_of else None,
                "start": state.start,
                "finish": state.finish,
                "duration_days": state.duration_days,
                "planned_cost": state.planned_cost,
                "actual_cost": state.actual_cost,
                "progress": state.progress_pct,
                "status": state.status,
                "assignments": [],
            },
        )
        task["assignments"].append(row)
        totals_by_type[resource.resource_type.value] += cost
        totals_by_stage[stage_of.get(state.external_id, "")] += cost
    daily = analytics.resource_daily_load()
    weeks: list[date] = []
    starts = [state.start for state in analytics.leaves() if state.start]
    finishes = [state.finish for state in analytics.leaves() if state.finish]
    if starts and finishes:
        week = _week_start(min(starts))
        while week <= max(finishes):
            weeks.append(week)
            week += timedelta(days=7)
    load_rows = []
    overallocations = []
    resources_payload = []
    for resource in analytics.resources:
        rows = sorted(assignments_by_resource.get(resource.id, []), key=lambda item: (item["start"] or date.max, _natural(item["external_id"])))
        human = resource.resource_type == ResourceType.HUMAN
        capacity = resource.capacity_hours_per_day or ZERO
        peak = ZERO
        over_days: list[date] = []
        days = daily.get(resource.id, {})
        for day, items in days.items():
            hours = sum((value for _, value in items), ZERO)
            if capacity and hours > capacity:
                over_days.append(day)
            if capacity:
                peak = max(peak, hours / capacity * HUNDRED)
        if human:
            week_cells = []
            for week in weeks:
                hours = ZERO
                contributing: dict[str, Decimal] = defaultdict(lambda: ZERO)
                working = 0
                for offset in range(7):
                    day = week + timedelta(days=offset)
                    if analytics.calendar.is_working_day(day):
                        working += 1
                    for task_id, value in days.get(day, []):
                        hours += value
                        contributing[task_id] += value
                cap = capacity * working
                week_cells.append(
                    {
                        "week": week,
                        "hours": hours,
                        "capacity": cap,
                        "pct": hours / cap * HUNDRED if cap else ZERO,
                        "tasks": [
                            {"external_id": task_id, "name": analytics.states[task_id].name, "hours": value}
                            for task_id, value in sorted(contributing.items(), key=lambda item: _natural(item[0]))
                        ],
                    }
                )
            load_rows.append({"resource_id": resource.id, "name": resource.name, "role": resource.role, "weeks": week_cells})
            if over_days:
                over_days.sort()
                involved: dict[str, Decimal] = defaultdict(lambda: ZERO)
                for day in over_days:
                    for task_id, value in days[day]:
                        involved[task_id] = max(involved[task_id], value)
                overallocations.append(
                    {
                        "resource_id": resource.id,
                        "resource": resource.name,
                        "from": over_days[0],
                        "to": over_days[-1],
                        "days": len(over_days),
                        "peak_pct": peak,
                        "tasks": [
                            {"external_id": task_id, "name": analytics.states[task_id].name, "hours_per_day": value}
                            for task_id, value in sorted(involved.items(), key=lambda item: _natural(item[0]))
                        ],
                    }
                )
        resources_payload.append(
            {
                "id": resource.id,
                "external_id": resource.external_id,
                "name": resource.name,
                "type": resource.resource_type.value,
                "role": resource.role,
                "rate": resource.rate,
                "unit": resource.unit,
                "capacity_hours_per_day": resource.capacity_hours_per_day,
                "user_id": resource.user_id,
                "user": user_names.get(resource.user_id) if resource.user_id else None,
                "total_hours": sum((row["hours"] or ZERO for row in rows), ZERO) if human else None,
                "total_quantity": None if human else sum((row["quantity"] or ZERO for row in rows), ZERO),
                "planned_cost": sum((row["cost"] for row in rows), ZERO),
                "task_count": len(rows),
                "peak_pct": peak,
                "overallocated_days": len(over_days),
                "assignments": rows,
            }
        )
    stage_names = {state.external_id: state.name for state in analytics.states.values() if state.kind == "ETAPA"}
    holidays = []
    from app.models import CalendarEntry

    for entry in session.scalars(
        sa.select(CalendarEntry).where(CalendarEntry.project_id == project_id).order_by(CalendarEntry.calendar_date)
    ).all():
        holidays.append({"date": entry.calendar_date, "type": entry.day_type.value, "description": entry.description})
    return ok(
        {
            "resources": resources_payload,
            "tasks": sorted(tasks.values(), key=lambda item: (item["start"] or date.max, _natural(item["external_id"]))),
            "weeks": weeks,
            "load": load_rows,
            "overallocations": overallocations,
            "totals_by_type": dict(totals_by_type),
            "totals_by_stage": [
                {"external_id": key, "name": stage_names.get(key, key), "cost": value}
                for key, value in sorted(totals_by_stage.items(), key=lambda item: _natural(item[0]))
            ],
            "total": sum(totals_by_type.values(), ZERO),
            "calendar": {
                "hours_per_day": project.working_hours_per_day,
                "working_days": project.working_days,
                "holidays": holidays,
            },
        }
    )


class AllocationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    element: str | None = Field(default=None, min_length=1, max_length=80)
    resource_id: uuid.UUID | None = None
    planned_hours: Decimal | None = Field(default=None, ge=0)
    quantity: Decimal | None = Field(default=None, ge=0)
    hours_per_day: Decimal | None = Field(default=None, ge=0, le=24)
    rate_override: Decimal | None = Field(default=None, ge=0)
    effort_driven: bool = False


def _allocation_result(session: Session, project: Project, element: GanttElement, effort_driven: bool, before: dict, names: dict, finish_before: dict) -> dict[str, Any]:
    session.flush()
    if effort_driven and element.element_type.value == "SUBACTIVIDAD":
        assignments = session.scalars(
            sa.select(Assignment).join(Resource, Assignment.resource_id == Resource.id).where(
                Assignment.element_id == element.id, Resource.resource_type == ResourceType.HUMAN
            )
        ).all()
        hours = sum((item.planned_hours for item in assignments), ZERO)
        daily = sum((item.hours_per_day for item in assignments if item.hours_per_day), ZERO)
        if hours > 0 and daily > 0:
            element.effort_hours = hours
            element.planned_finish = None
    _recalculate(session, project)
    after = _snapshot(session, project.id)
    analytics = _commit_with_kpis(session, project)
    return ok({"changes": _diff(before, after, names), "finish_before": finish_before, "finish_after": analytics.project_finish()})


def _allocation_context(session: Session, project: Project) -> tuple[dict, dict, dict]:
    before = _snapshot(session, project.id)
    names = {e.external_id: e.name for e in session.scalars(sa.select(GanttElement).where(GanttElement.project_id == project.id)).all()}
    return before, names, ProjectAnalytics(session, project).project_finish()


@router.post("/projects/{project_id}/allocations", status_code=201)
def create_allocation(project_id: uuid.UUID, payload: AllocationInput, session: Session = Depends(get_db), actor: Manager = None) -> dict[str, Any]:
    project = require_project(session, project_id)
    if not payload.element or payload.resource_id is None:
        raise ApiError("VALIDATION_ERROR", "Debe indicar la tarea y el recurso")
    element = _require_element(session, project_id, payload.element)
    if element.element_type.value != "SUBACTIVIDAD":
        raise ApiError("INVALID_ASSIGNMENT", "Solo se asignan recursos a subactividades")
    resource = session.scalar(sa.select(Resource).where(Resource.id == payload.resource_id, Resource.project_id == project_id))
    if resource is None:
        raise ApiError("NOT_FOUND", "Recurso no encontrado", 404)
    if session.scalar(sa.select(Assignment).where(Assignment.element_id == element.id, Assignment.resource_id == resource.id)):
        raise ApiError("CONFLICT", "El recurso ya está asignado a la tarea; edite la asignación", 409)
    human = resource.resource_type == ResourceType.HUMAN
    if human and not payload.planned_hours:
        raise ApiError("VALIDATION_ERROR", "Indique las horas planificadas")
    if not human and not payload.quantity:
        raise ApiError("VALIDATION_ERROR", "Indique la cantidad")
    before, names, finish_before = _allocation_context(session, project)
    session.add(
        Assignment(
            project_id=project_id,
            element_id=element.id,
            resource_id=resource.id,
            planned_hours=payload.planned_hours or ZERO,
            quantity=payload.quantity or ZERO,
            hours_per_day=payload.hours_per_day or (resource.capacity_hours_per_day if human else ZERO) or ZERO,
            rate_override=payload.rate_override,
        )
    )
    record_audit(
        session, user_id=actor.id, action="CREATE", entity_type="ASSIGNMENT", entity_id=element.id,
        after_data=json_value({"task": element.external_id, "resource": resource.external_id, **payload.model_dump(exclude_unset=True)}),
    )
    return _allocation_result(session, project, element, payload.effort_driven, before, names, finish_before)


@router.patch("/projects/{project_id}/allocations/{allocation_id}")
def update_allocation(
    project_id: uuid.UUID, allocation_id: uuid.UUID, payload: AllocationInput, session: Session = Depends(get_db), actor: Manager = None
) -> dict[str, Any]:
    project = require_project(session, project_id)
    assignment = session.scalar(sa.select(Assignment).where(Assignment.id == allocation_id, Assignment.project_id == project_id))
    if assignment is None:
        raise ApiError("NOT_FOUND", "Asignación no encontrada", 404)
    element = session.get(GanttElement, assignment.element_id)
    before, names, finish_before = _allocation_context(session, project)
    data = payload.model_dump(exclude_unset=True, exclude={"element", "effort_driven"})
    if "resource_id" in data and data["resource_id"] is not None:
        resource = session.scalar(sa.select(Resource).where(Resource.id == data["resource_id"], Resource.project_id == project_id))
        if resource is None:
            raise ApiError("NOT_FOUND", "Recurso no encontrado", 404)
    previous = {key: getattr(assignment, key) for key in data}
    for key, value in data.items():
        if value is not None or key == "rate_override":
            setattr(assignment, key, value)
    record_audit(
        session, user_id=actor.id, action="UPDATE", entity_type="ASSIGNMENT", entity_id=assignment.id,
        before_data=json_value(previous), after_data=json_value(data),
    )
    return _allocation_result(session, project, element, payload.effort_driven, before, names, finish_before)


@router.delete("/projects/{project_id}/allocations/{allocation_id}")
def delete_allocation(project_id: uuid.UUID, allocation_id: uuid.UUID, session: Session = Depends(get_db), actor: Manager = None) -> dict[str, Any]:
    project = require_project(session, project_id)
    assignment = session.scalar(sa.select(Assignment).where(Assignment.id == allocation_id, Assignment.project_id == project_id))
    if assignment is None:
        raise ApiError("NOT_FOUND", "Asignación no encontrada", 404)
    element = session.get(GanttElement, assignment.element_id)
    before, names, finish_before = _allocation_context(session, project)
    record_audit(session, user_id=actor.id, action="DELETE", entity_type="ASSIGNMENT", entity_id=assignment.id)
    session.delete(assignment)
    return _allocation_result(session, project, element, False, before, names, finish_before)


class ResourceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    external_id: str | None = Field(default=None, min_length=1, max_length=80)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    resource_type: ResourceType | None = None
    role: str | None = Field(default=None, max_length=160)
    rate: Decimal | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=40)
    capacity_hours_per_day: Decimal | None = Field(default=None, ge=0, le=24)
    user_id: uuid.UUID | None = None


@router.post("/projects/{project_id}/resources-admin", status_code=201)
def create_resource_admin(project_id: uuid.UUID, payload: ResourceInput, session: Session = Depends(get_db), actor: Manager = None) -> dict[str, Any]:
    require_project(session, project_id)
    if not payload.external_id or not payload.name or payload.resource_type is None:
        raise ApiError("VALIDATION_ERROR", "ID, nombre y tipo son obligatorios")
    if session.scalar(sa.select(Resource).where(Resource.project_id == project_id, Resource.external_id == payload.external_id)):
        raise ApiError("CONFLICT", "Ya existe un recurso con ese ID", 409)
    resource = Resource(project_id=project_id, **payload.model_dump(exclude_unset=True))
    if resource.resource_type == ResourceType.HUMAN and resource.capacity_hours_per_day is None:
        resource.capacity_hours_per_day = Decimal("8")
    session.add(resource)
    session.flush()
    record_audit(session, user_id=actor.id, action="CREATE", entity_type="RESOURCE", entity_id=resource.id, after_data={"name": resource.name})
    session.commit()
    return ok({"id": resource.id})


@router.patch("/projects/{project_id}/resources-admin/{resource_id}")
def update_resource_admin(
    project_id: uuid.UUID, resource_id: uuid.UUID, payload: ResourceInput, session: Session = Depends(get_db), actor: Manager = None
) -> dict[str, Any]:
    project = require_project(session, project_id)
    resource = session.scalar(sa.select(Resource).where(Resource.id == resource_id, Resource.project_id == project_id))
    if resource is None:
        raise ApiError("NOT_FOUND", "Recurso no encontrado", 404)
    data = payload.model_dump(exclude_unset=True)
    data.pop("external_id", None)
    previous = {key: getattr(resource, key) for key in data}
    for key, value in data.items():
        setattr(resource, key, value)
    record_audit(session, user_id=actor.id, action="UPDATE", entity_type="RESOURCE", entity_id=resource.id, before_data=json_value(previous), after_data=json_value(data))
    session.flush()
    if {"rate", "capacity_hours_per_day"} & set(data) and _has_plan(session, project):
        _recalculate(session, project)
        _commit_with_kpis(session, project)
    else:
        session.commit()
    return ok({"id": resource.id})


# ========================================================= milestones
@router.get("/projects/{project_id}/milestones")
def milestones(project_id: uuid.UUID, session: Session = Depends(get_db), _: CurrentUser = None) -> dict[str, Any]:
    project = require_project(session, project_id)
    analytics = ProjectAnalytics(session, project)
    users = _user_names(session)
    payload = []
    milestone_ids = [state.id for state in analytics.milestones()]
    criteria_rows = session.scalars(
        sa.select(AcceptanceCriterion).where(AcceptanceCriterion.milestone_id.in_(milestone_ids)).order_by(AcceptanceCriterion.external_id)
    ).all() if milestone_ids else []
    criteria_by_milestone: dict[uuid.UUID, list[AcceptanceCriterion]] = defaultdict(list)
    for row in criteria_rows:
        criteria_by_milestone[row.milestone_id].append(row)
    evidences: dict[uuid.UUID, list[Evidence]] = defaultdict(list)
    if criteria_rows:
        for evidence in session.scalars(
            sa.select(Evidence).where(Evidence.criterion_id.in_([row.id for row in criteria_rows])).order_by(Evidence.uploaded_at)
        ).all():
            evidences[evidence.criterion_id].append(evidence)
    links = session.scalars(sa.select(MilestoneTask).where(MilestoneTask.milestone_id.in_(milestone_ids))).all() if milestone_ids else []
    tasks_by_milestone: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for link in links:
        tasks_by_milestone[link.milestone_id].append(link.element_id)
    state_by_id = {state.id: state for state in analytics.states.values()}
    acceptance = {row.element_id: row.acceptance_status.value for row in session.scalars(sa.select(Milestone).where(Milestone.element_id.in_(milestone_ids))).all()} if milestone_ids else {}
    for state in analytics.milestones():
        linked = {state_by_id[item].external_id for item in tasks_by_milestone.get(state.id, []) if item in state_by_id}
        linked |= {item["predecessor"] for item in state.predecessors}
        task_rows = []
        for external_id in sorted(linked, key=_natural):
            task = analytics.states.get(external_id)
            if task is None:
                continue
            parent = analytics.states.get(task.parent_external_id) if task.parent_external_id else None
            task_rows.append(
                {
                    "external_id": task.external_id,
                    "name": task.name,
                    "kind": task.kind,
                    "activity": parent.name if parent else None,
                    "progress": task.progress_pct,
                    "status": task.status,
                    "status_label": STATUS_LABELS.get(task.status, task.status),
                    "finish": task.finish,
                    "forecast_finish": task.forecast_finish,
                }
            )
        criteria = [
            {
                "id": row.id,
                "external_id": row.external_id,
                "description": row.description,
                "verification_method": row.verification_method,
                "responsible": row.responsible_label,
                "status": row.status.value,
                "verified_by": users.get(row.verified_by) if row.verified_by else None,
                "verified_at": row.verified_at,
                "notes": row.notes,
                "evidences": [
                    {"id": item.id, "file_name": item.file_name, "uploaded_at": item.uploaded_at, "size": item.size_bytes, "uploaded_by": users.get(item.uploaded_by) if item.uploaded_by else None}
                    for item in evidences.get(row.id, [])
                ],
            }
            for row in criteria_by_milestone.get(state.id, [])
        ]
        parent = analytics.states.get(state.parent_external_id) if state.parent_external_id else None
        stage = parent
        while stage is not None and stage.parent_external_id:
            stage = analytics.states.get(stage.parent_external_id)
        payload.append(
            {
                "id": state.id,
                "external_id": state.external_id,
                "name": state.name,
                "activity": parent.name if parent else None,
                "stage": stage.name if stage else None,
                "baseline_finish": state.baseline_finish or state.finish,
                "finish": state.finish,
                "forecast_finish": state.forecast_finish,
                "actual_finish": state.actual_finish,
                "progress": state.progress_pct,
                "status": state.status,
                "status_label": {"COMPLETADA": "Cumplido", "COMPLETADA_ATRASO": "Cumplido con atraso", "EN_RIESGO": "En riesgo", "ATRASADA": "Atrasado"}.get(state.status, "Pendiente"),
                "slip_days": state.slip_days,
                "is_critical": state.is_critical,
                "acceptance_status": acceptance.get(state.id, "PENDIENTE"),
                "criteria_met": sum(1 for item in criteria if item["status"] == "CUMPLIDO"),
                "criteria_total": len(criteria),
                "criteria": criteria,
                "tasks": task_rows,
            }
        )
    metrics = analytics.metrics()
    done = [item for item in payload if item["progress"] >= HUNDRED]
    return ok(
        {
            "cutoff": analytics.cutoff,
            "milestones": payload,
            "summary": {
                "total": len(payload),
                "done": len(done),
                "on_time_pct": metrics["MILESTONES_ON_TIME_PCT"],
                "at_risk": sum(1 for item in payload if item["status"] in {"EN_RIESGO", "ATRASADA"}),
                "closing_deviation": metrics["CLOSING_MILESTONE_DEVIATION"],
            },
        }
    )


class CriterionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: CriterionStatus
    notes: str | None = Field(default=None, max_length=1000)


@router.post("/criteria/{criterion_id}/status")
def set_criterion_status(criterion_id: uuid.UUID, payload: CriterionCommand, session: Session = Depends(get_db), actor: Manager = None) -> dict[str, Any]:
    criterion = session.get(AcceptanceCriterion, criterion_id)
    if criterion is None:
        raise ApiError("NOT_FOUND", "Criterio no encontrado", 404)
    element = session.get(GanttElement, criterion.milestone_id)
    project = require_project(session, element.project_id)
    previous = criterion.status.value
    criterion.status = payload.status
    criterion.notes = payload.notes
    criterion.verified_by = actor.id if payload.status != CriterionStatus.PENDING else None
    criterion.verified_at = datetime.now(UTC) if payload.status != CriterionStatus.PENDING else None
    session.flush()
    all_criteria = session.scalars(sa.select(AcceptanceCriterion).where(AcceptanceCriterion.milestone_id == element.id)).all()
    milestone = session.get(Milestone, element.id)
    if all(item.status == CriterionStatus.MET for item in all_criteria):
        acceptance = CriterionStatus.MET
    elif any(item.status == CriterionStatus.NOT_MET for item in all_criteria):
        acceptance = CriterionStatus.NOT_MET
    else:
        acceptance = CriterionStatus.PENDING
    if milestone is not None:
        milestone.acceptance_status = acceptance
    if acceptance == CriterionStatus.MET and element.progress_pct < HUNDRED:
        element.progress_pct = HUNDRED
        reference = project.cutoff_date or date.today()
        element.actual_finish = reference
        element.actual_start = reference
    elif acceptance != CriterionStatus.MET and element.progress_pct >= HUNDRED:
        element.progress_pct = ZERO
        element.actual_finish = None
        element.actual_start = None
    record_audit(
        session, user_id=actor.id, action="VERIFY", entity_type="ACCEPTANCE_CRITERION", entity_id=criterion.id,
        before_data={"status": previous}, after_data={"status": payload.status.value, "milestone": acceptance.value},
    )
    session.flush()
    _recalculate(session, project)
    _commit_with_kpis(session, project)
    return ok({"criterion": criterion.status.value, "milestone_acceptance": acceptance.value})


class CriterionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(min_length=1, max_length=1000)
    verification_method: str = Field(min_length=1, max_length=500)
    responsible: str | None = Field(default=None, max_length=200)


@router.post("/projects/{project_id}/milestones/{milestone}/criteria", status_code=201)
def add_criterion(project_id: uuid.UUID, milestone: str, payload: CriterionInput, session: Session = Depends(get_db), actor: Manager = None) -> dict[str, Any]:
    require_project(session, project_id)
    element = _require_element(session, project_id, milestone)
    if element.element_type != GanttElementType.MILESTONE:
        raise ApiError("VALIDATION_ERROR", "El elemento no es un hito")
    if session.get(Milestone, element.id) is None:
        session.add(Milestone(element_id=element.id))
        session.flush()
    count = session.scalar(sa.select(sa.func.count(AcceptanceCriterion.id)).where(AcceptanceCriterion.milestone_id == element.id)) or 0
    criterion = AcceptanceCriterion(
        milestone_id=element.id,
        external_id=f"CR-{element.external_id}-{count + 1:02d}",
        description=payload.description,
        verification_method=payload.verification_method,
        responsible_label=payload.responsible,
    )
    session.add(criterion)
    session.flush()
    record_audit(session, user_id=actor.id, action="CREATE", entity_type="ACCEPTANCE_CRITERION", entity_id=criterion.id, after_data={"description": criterion.description})
    session.commit()
    return ok({"id": criterion.id, "external_id": criterion.external_id})


# =========================================================== evidences
def _store_upload(upload: UploadFile) -> tuple[str, str, int]:
    name = Path(upload.filename or "archivo").name
    content = upload.file.read(MAX_UPLOAD + 1)
    if len(content) > MAX_UPLOAD:
        raise ApiError("FILE_TOO_LARGE", "El archivo excede 15 MB")
    if not content:
        raise ApiError("EMPTY_FILE", "El archivo está vacío")
    key = f"{uuid.uuid4().hex}{Path(name).suffix.lower()[:10]}"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (UPLOAD_DIR / key).write_bytes(content)
    return name, key, len(content)


@router.post("/criteria/{criterion_id}/files", status_code=201)
def upload_criterion_file(criterion_id: uuid.UUID, file: UploadFile = File(...), session: Session = Depends(get_db), actor: CurrentUser = None) -> dict[str, Any]:
    criterion = session.get(AcceptanceCriterion, criterion_id)
    if criterion is None:
        raise ApiError("NOT_FOUND", "Criterio no encontrado", 404)
    name, key, size = _store_upload(file)
    evidence = Evidence(criterion_id=criterion.id, file_name=name, storage_key=key, content_type=file.content_type, size_bytes=size, uploaded_by=actor.id)
    session.add(evidence)
    session.flush()
    record_audit(session, user_id=actor.id, action="UPLOAD", entity_type="EVIDENCE", entity_id=evidence.id, after_data={"file_name": name})
    session.commit()
    return ok({"id": evidence.id, "file_name": name})


@router.post("/change-requests/{request_id}/files", status_code=201)
def upload_change_file(
    request_id: uuid.UUID,
    file: UploadFile = File(...),
    description: str | None = Form(default=None),
    session: Session = Depends(get_db),
    actor: CurrentUser = None,
) -> dict[str, Any]:
    request = session.get(ChangeRequest, request_id)
    if request is None:
        raise ApiError("NOT_FOUND", "Solicitud no encontrada", 404)
    name, key, size = _store_upload(file)
    evidence = Evidence(change_request_id=request.id, file_name=name, storage_key=key, content_type=file.content_type, size_bytes=size, uploaded_by=actor.id)
    session.add(evidence)
    session.flush()
    record_audit(session, user_id=actor.id, action="UPLOAD", entity_type="EVIDENCE", entity_id=evidence.id, after_data={"file_name": name, "description": description})
    project = require_project(session, request.project_id)
    _commit_with_kpis(session, project)
    return ok({"id": evidence.id, "file_name": name})


@router.get("/evidences/{evidence_id}/file")
def download_evidence(evidence_id: uuid.UUID, session: Session = Depends(get_db), _: CurrentUser = None) -> Any:
    evidence = session.get(Evidence, evidence_id)
    if evidence is None:
        raise ApiError("NOT_FOUND", "Evidencia no encontrada", 404)
    path = UPLOAD_DIR / Path(evidence.storage_key).name
    if not path.exists():
        content = (
            f"Evidencia de demostración: {evidence.file_name}\n"
            "El archivo original no está en este servidor (dato semilla).\n"
        ).encode()
        return Response(content, media_type="text/plain; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{evidence.file_name}.txt"'})
    media = evidence.content_type or mimetypes.guess_type(evidence.file_name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media, filename=evidence.file_name)


@router.delete("/evidences/{evidence_id}")
def delete_evidence(evidence_id: uuid.UUID, session: Session = Depends(get_db), actor: Manager = None) -> dict[str, Any]:
    evidence = session.get(Evidence, evidence_id)
    if evidence is None:
        raise ApiError("NOT_FOUND", "Evidencia no encontrada", 404)
    record_audit(session, user_id=actor.id, action="DELETE", entity_type="EVIDENCE", entity_id=evidence.id, after_data={"file_name": evidence.file_name})
    session.delete(evidence)
    session.commit()
    return ok({"deleted": True})


# ================================================================ KPI
CATEGORY_LABEL = {"PROYECTO": "Proyecto e hitos", "CAMBIO": "Gestión del cambio"}


@router.get("/projects/{project_id}/kpis/board")
def kpi_board(project_id: uuid.UUID, session: Session = Depends(get_db), _: CurrentUser = None) -> dict[str, Any]:
    project = require_project(session, project_id)
    analytics = ProjectAnalytics(session, project)
    metrics = analytics.metrics()
    codes = variable_codes(session, project_id)
    users = _user_names(session)
    kpis = session.scalars(sa.select(Kpi).where(Kpi.project_id == project_id).order_by(Kpi.category.desc(), Kpi.code)).all()
    history_rows = session.scalars(
        sa.select(KpiValue).join(Kpi, KpiValue.kpi_id == Kpi.id).where(Kpi.project_id == project_id, KpiValue.element_id.is_(None)).order_by(KpiValue.cutoff_at)
    ).all()
    history: dict[uuid.UUID, list[dict[str, Any]]] = defaultdict(list)
    for row in history_rows:
        history[row.kpi_id].append({"cutoff": row.cutoff_at.date(), "value": row.value})
    versions: dict[uuid.UUID, list[dict[str, Any]]] = defaultdict(list)
    for version in session.scalars(
        sa.select(KpiFormulaVersion).join(Kpi, KpiFormulaVersion.kpi_id == Kpi.id).where(Kpi.project_id == project_id).order_by(KpiFormulaVersion.version)
    ).all():
        versions[version.kpi_id].append(
            {"version": version.version, "formula": version.formula, "previous": version.previous_formula, "changed_by": users.get(version.changed_by) if version.changed_by else None, "changed_at": version.changed_at}
        )
    catalog = {definition.code: definition for definition in DEFAULT_KPI_VARIABLES}
    payload = []
    for kpi in kpis:
        value, breakdown = evaluate(kpi.formula, metrics, codes)
        breakdown["variables_detail"] = [
            {
                "code": code,
                "value": json_value(len(metrics[code]) if isinstance(metrics.get(code), list) else metrics.get(code)),
                "description": catalog[code].description if code in catalog else code,
                "source": catalog[code].source if code in catalog else "Variable del proyecto",
                "calculation": catalog[code].calculation_method if code in catalog else "",
            }
            for code in breakdown.get("variables", {})
        ]
        payload.append(
            {
                "id": kpi.id,
                "code": kpi.code,
                "name": kpi.name,
                "description": kpi.description,
                "formula": kpi.formula,
                "category": kpi.category,
                "category_label": CATEGORY_LABEL.get(kpi.category, kpi.category),
                "is_additional": kpi.is_additional,
                "unit": kpi.unit,
                "scope": kpi.scope.value,
                "target": kpi.target,
                "green_threshold": kpi.green_threshold,
                "yellow_threshold": kpi.yellow_threshold,
                "frequency": kpi.frequency,
                "alert_rule": kpi.alert_rule,
                "is_active": kpi.is_active,
                "value": value,
                "status": kpi_status(value, kpi.green_threshold, kpi.yellow_threshold) if kpi.is_active else "INACTIVO",
                "direction": "MAYOR" if (kpi.green_threshold or ZERO) >= (kpi.yellow_threshold or ZERO) else "MENOR",
                "breakdown": breakdown,
                "history": history.get(kpi.id, []),
                "versions": versions.get(kpi.id, []),
            }
        )
    variables = [
        {
            "code": definition.code,
            "description": definition.description,
            "source": definition.source,
            "calculation": definition.calculation_method,
            "type": definition.data_type,
            "value": json_value(len(metrics[definition.code]) if isinstance(metrics.get(definition.code), list) else metrics.get(definition.code)),
        }
        for definition in DEFAULT_KPI_VARIABLES
        if not definition.code.startswith("VALOR_")
    ]
    manual = {row.code: row for row in session.scalars(sa.select(ManualMetric).where(ManualMetric.project_id == project_id)).all()}
    return ok(
        {
            "cutoff": analytics.cutoff,
            "kpis": payload,
            "variables": variables,
            "manual": [
                {"code": code, "label": label, "value": manual[code].value if code in manual else ZERO, "updated_at": manual[code].updated_at if code in manual else None}
                for code, label in MANUAL_METRICS.items()
            ],
        }
    )


class FormulaTest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    formula: str = Field(min_length=1, max_length=2000)


@router.post("/projects/{project_id}/kpis/test")
def test_formula(project_id: uuid.UUID, payload: FormulaTest, session: Session = Depends(get_db), _: CurrentUser = None) -> dict[str, Any]:
    project = require_project(session, project_id)
    codes = variable_codes(session, project_id)
    try:
        validate_formula(payload.formula, codes)
    except KpiFormulaError as error:
        raise ApiError("INVALID_KPI_FORMULA", str(error)) from error
    analytics = ProjectAnalytics(session, project)
    value, breakdown = evaluate(payload.formula, analytics.metrics(), codes)
    if value is None:
        raise ApiError("INVALID_KPI_FORMULA", breakdown.get("error", "No se pudo evaluar la fórmula"))
    return ok({"value": value, "breakdown": breakdown})


class KpiConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str | None = Field(default=None, min_length=1, max_length=80)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    formula: str | None = Field(default=None, min_length=1, max_length=2000)
    category: str | None = Field(default=None, pattern=r"^(PROYECTO|CAMBIO)$")
    is_additional: bool | None = None
    unit: str | None = Field(default=None, max_length=20)
    scope: KpiScope | None = None
    target: Decimal | None = None
    green_threshold: Decimal | None = None
    yellow_threshold: Decimal | None = None
    frequency: str | None = Field(default=None, max_length=40)
    alert_rule: str | None = Field(default=None, max_length=1000)
    is_active: bool | None = None


@router.put("/projects/{project_id}/kpi-config/{kpi_id}")
def update_kpi_config(project_id: uuid.UUID, kpi_id: uuid.UUID, payload: KpiConfig, session: Session = Depends(get_db), actor: Manager = None) -> dict[str, Any]:
    project = require_project(session, project_id)
    kpi = session.scalar(sa.select(Kpi).where(Kpi.id == kpi_id, Kpi.project_id == project_id))
    if kpi is None:
        raise ApiError("NOT_FOUND", "KPI no encontrado", 404)
    data = payload.model_dump(exclude_unset=True)
    data.pop("code", None)
    if "formula" in data:
        try:
            validate_formula(data["formula"], variable_codes(session, project_id))
        except KpiFormulaError as error:
            raise ApiError("INVALID_KPI_FORMULA", str(error)) from error
        if data["formula"] != kpi.formula:
            latest = session.scalar(sa.select(sa.func.max(KpiFormulaVersion.version)).where(KpiFormulaVersion.kpi_id == kpi.id)) or 0
            session.add(KpiFormulaVersion(kpi_id=kpi.id, version=int(latest) + 1, formula=data["formula"], previous_formula=kpi.formula, changed_by=actor.id))
    previous = {key: getattr(kpi, key) for key in data}
    for key, value in data.items():
        setattr(kpi, key, value)
    record_audit(session, user_id=actor.id, action="UPDATE", entity_type="KPI", entity_id=kpi.id, before_data=json_value(previous), after_data=json_value(data))
    session.flush()
    _commit_with_kpis(session, project)
    return ok({"id": kpi.id})


@router.post("/projects/{project_id}/kpi-config", status_code=201)
def create_kpi_config(project_id: uuid.UUID, payload: KpiConfig, session: Session = Depends(get_db), actor: Manager = None) -> dict[str, Any]:
    project = require_project(session, project_id)
    if not payload.code or not payload.name or not payload.formula:
        raise ApiError("VALIDATION_ERROR", "Código, nombre y fórmula son obligatorios")
    if session.scalar(sa.select(Kpi).where(Kpi.project_id == project_id, Kpi.code == payload.code)):
        raise ApiError("CONFLICT", "Ya existe un KPI con ese código", 409)
    try:
        validate_formula(payload.formula, variable_codes(session, project_id))
    except KpiFormulaError as error:
        raise ApiError("INVALID_KPI_FORMULA", str(error)) from error
    data = payload.model_dump(exclude_unset=True)
    data.setdefault("scope", KpiScope.PROJECT)
    kpi = Kpi(project_id=project_id, **data)
    session.add(kpi)
    session.flush()
    session.add(KpiFormulaVersion(kpi_id=kpi.id, version=1, formula=kpi.formula, changed_by=actor.id))
    record_audit(session, user_id=actor.id, action="CREATE", entity_type="KPI", entity_id=kpi.id, after_data={"code": kpi.code})
    session.flush()
    _commit_with_kpis(session, project)
    return ok({"id": kpi.id})


class ManualInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=80)
    value: Decimal


@router.put("/projects/{project_id}/manual-metrics")
def set_manual_metric(project_id: uuid.UUID, payload: ManualInput, session: Session = Depends(get_db), actor: Manager = None) -> dict[str, Any]:
    project = require_project(session, project_id)
    code = payload.code.upper()
    row = session.scalar(sa.select(ManualMetric).where(ManualMetric.project_id == project_id, ManualMetric.code == code))
    if row is None:
        row = ManualMetric(project_id=project_id, code=code)
        session.add(row)
    previous = row.value
    row.value = payload.value
    row.updated_by = actor.id
    row.updated_at = datetime.now(UTC)
    record_audit(session, user_id=actor.id, action="UPDATE", entity_type="MANUAL_METRIC", entity_id=project_id, before_data={"code": code, "value": json_value(previous)}, after_data={"code": code, "value": json_value(payload.value)})
    session.flush()
    _commit_with_kpis(session, project)
    return ok({"code": code, "value": payload.value})


@router.post("/projects/{project_id}/kpis/snapshot")
def snapshot_kpis(project_id: uuid.UUID, session: Session = Depends(get_db), _: Manager = None) -> dict[str, Any]:
    project = require_project(session, project_id)
    values = recalculate_kpis(session, project)
    session.commit()
    return ok({"count": len(values)})


# ===================================================== change control
TYPE_LABEL = {"ALCANCE": "Alcance", "PLAZO": "Plazo", "COSTO": "Costo", "RECURSOS": "Recursos"}
STATUS_LABEL = {"ABIERTA": "Abierta", "APROBADA": "Aprobada", "RECHAZADA": "Rechazada", "CANCELADA": "Cancelada", "CERRADA": "Cerrada"}


def _change_row(session: Session, request: ChangeRequest, analytics: ProjectAnalytics, users: dict) -> dict[str, Any]:
    flow = ChangeFlow(session, request, None)
    stages = flow.stages()
    active = next((item for item in stages if item.record.status == ChangeStageStatus.ACTIVE), None)
    current = active or next((item for item in stages if item.stage.id == request.current_stage_id), None)
    latest = session.scalar(
        sa.select(ChangeImpact).where(ChangeImpact.request_id == request.id).order_by(ChangeImpact.simulated_at.desc()).limit(1)
    )
    evidences = session.scalar(sa.select(sa.func.count(Evidence.id)).where(Evidence.change_request_id == request.id)) or 0
    completed = sum(1 for item in stages if item.record.status == ChangeStageStatus.COMPLETED)
    return {
        "id": request.id,
        "code": request.code,
        "title": request.title,
        "description": request.description,
        "justification": request.justification,
        "type": request.change_type.value,
        "type_label": TYPE_LABEL.get(request.change_type.value),
        "priority": request.priority.value,
        "status": request.status.value,
        "status_label": STATUS_LABEL.get(request.status.value),
        "requester": users.get(request.requester_id) if request.requester_id else None,
        "requester_area": request.requester_area,
        "responsible": users.get(request.responsible_id) if request.responsible_id else None,
        "responsible_id": request.responsible_id,
        "stage_sequence": current.stage.sequence if current else None,
        "stage_name": current.stage.name if current else None,
        "stages_completed": completed,
        "stages_total": len(stages),
        "sla_breached": bool(active and analytics.sla_breached(request)),
        "delta_days": latest.delta_schedule_days if latest else None,
        "delta_cost": latest.delta_cost if latest else None,
        "evidences": evidences,
        "applied": flow.applied(),
        "created_at": request.created_at,
        "decided_at": request.decided_at,
        "closed_at": request.closed_at,
    }


@router.get("/projects/{project_id}/change-board")
def change_board(project_id: uuid.UUID, session: Session = Depends(get_db), _: CurrentUser = None) -> dict[str, Any]:
    project = require_project(session, project_id)
    analytics = ProjectAnalytics(session, project)
    users = _user_names(session)
    stages = ensure_stages(session, project_id)
    session.commit()
    requests = session.scalars(sa.select(ChangeRequest).where(ChangeRequest.project_id == project_id).order_by(ChangeRequest.code)).all()
    rows = [_change_row(session, request, analytics, users) for request in requests]
    return ok(
        {
            "requests": rows,
            "stages": [{"id": stage.id, "name": stage.name, "sequence": stage.sequence, "sla_hours": stage.sla_hours} for stage in stages],
            "users": [{"id": user_id, "name": name} for user_id, name in users.items()],
        }
    )


@router.get("/change-requests/{request_id}/detail")
def change_detail(request_id: uuid.UUID, session: Session = Depends(get_db), _: CurrentUser = None) -> dict[str, Any]:
    request = session.get(ChangeRequest, request_id)
    if request is None:
        raise ApiError("NOT_FOUND", "Solicitud no encontrada", 404)
    project = require_project(session, request.project_id)
    analytics = ProjectAnalytics(session, project)
    users = _user_names(session)
    flow = ChangeFlow(session, request, None)
    stage_rows = []
    now = project_clock(project)
    for item in flow.stages():
        elapsed = None
        if item.record.entered_at:
            end = item.record.exited_at or now
            elapsed = (end - item.record.entered_at).total_seconds() / 3600
        stage_rows.append(
            {
                "sequence": item.stage.sequence,
                "name": item.stage.name,
                "status": item.record.status.value,
                "entered_at": item.record.entered_at,
                "exited_at": item.record.exited_at,
                "sla_hours": item.stage.sla_hours,
                "elapsed_hours": elapsed,
                "breached": bool(item.stage.sla_hours and elapsed and elapsed > item.stage.sla_hours),
                "completed_by": users.get(item.record.completed_by) if item.record.completed_by else None,
                "notes": item.record.notes,
            }
        )
    stage_names = {stage.id: stage.name for stage in session.scalars(sa.select(ChangeStage).where(ChangeStage.project_id == project.id)).all()}
    transitions = [
        {
            "occurred_at": row.occurred_at,
            "from_stage": stage_names.get(row.from_stage_id),
            "to_stage": stage_names.get(row.to_stage_id),
            "from_status": row.from_status.value if row.from_status else None,
            "to_status": row.to_status.value,
            "by": users.get(row.performed_by) if row.performed_by else None,
            "comment": row.comment,
        }
        for row in session.scalars(sa.select(ChangeTransition).where(ChangeTransition.request_id == request.id).order_by(ChangeTransition.occurred_at)).all()
    ]
    audit = [
        {"occurred_at": row.occurred_at, "action": row.action, "by": users.get(row.user_id) if row.user_id else None, "data": row.after_data}
        for row in session.scalars(
            sa.select(AuditLog).where(AuditLog.entity_id == request.id).order_by(AuditLog.occurred_at)
        ).all()
    ]
    impacts = [
        {
            "id": row.id,
            "simulated_at": row.simulated_at,
            "proposed_finish": row.proposed_project_finish,
            "delta_days": row.delta_schedule_days,
            "delta_cost": row.delta_cost,
            "affected": row.affected_elements,
            "resources": row.resource_effect,
            "summary": row.summary,
        }
        for row in session.scalars(sa.select(ChangeImpact).where(ChangeImpact.request_id == request.id).order_by(ChangeImpact.simulated_at.desc())).all()
    ]
    evidences = [
        {"id": row.id, "file_name": row.file_name, "uploaded_at": row.uploaded_at, "size": row.size_bytes, "uploaded_by": users.get(row.uploaded_by) if row.uploaded_by else None}
        for row in session.scalars(sa.select(Evidence).where(Evidence.change_request_id == request.id).order_by(Evidence.uploaded_at)).all()
    ]
    preview = None
    if request.proposal and not flow.applied() and request.status in {ChangeStatus.OPEN, ChangeStatus.APPROVED}:
        try:
            preview = simulate_proposal(session, project, list(request.proposal))
        except (ValueError, KeyError) as error:
            preview = {"error": str(error)}
    leaves = [
        {"external_id": state.external_id, "name": state.name, "duration_days": state.duration_days, "is_critical": state.is_critical}
        for state, _ in ordered_states(analytics)
        if state.kind == "SUBACTIVIDAD"
    ]
    resources = [{"external_id": row.external_id, "name": row.name, "type": row.resource_type.value, "rate": row.rate} for row in analytics.resources]
    return ok(
        {
            "request": _change_row(session, request, analytics, users),
            "proposal": request.proposal or [],
            "stages": stage_rows,
            "transitions": transitions,
            "audit": audit,
            "impacts": impacts,
            "preview": preview,
            "evidences": evidences,
            "contingency_amount": analytics.contingency_amount(),
            "tasks": leaves,
            "resources": resources,
            "committed_finish": project.committed_finish,
        }
    )


class ChangeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=3, max_length=300)
    description: str = Field(min_length=3, max_length=4000)
    justification: str | None = Field(default=None, max_length=4000)
    change_type: ChangeType
    priority: ChangePriority = ChangePriority.MEDIUM
    requester_area: str | None = Field(default=None, max_length=160)
    responsible_id: uuid.UUID | None = None


@router.post("/projects/{project_id}/change-requests-v2", status_code=201)
def create_change_v2(project_id: uuid.UUID, payload: ChangeInput, session: Session = Depends(get_db), actor: CurrentUser = None) -> dict[str, Any]:
    require_project(session, project_id)
    stages = ensure_stages(session, project_id)
    count = session.scalar(sa.select(sa.func.count(ChangeRequest.id)).where(ChangeRequest.project_id == project_id)) or 0
    code = f"SC-{count + 1:02d}"
    while session.scalar(sa.select(ChangeRequest).where(ChangeRequest.project_id == project_id, ChangeRequest.code == code)):
        count += 1
        code = f"SC-{count + 1:02d}"
    project = require_project(session, project_id)
    now = project_clock(project)
    request = ChangeRequest(project_id=project_id, code=code, requester_id=actor.id, current_stage_id=stages[0].id, proposal=[], created_at=now, updated_at=now, **payload.model_dump())
    session.add(request)
    session.flush()
    session.add_all(
        [
            ChangeRequestStage(
                request_id=request.id,
                stage_id=stage.id,
                status=ChangeStageStatus.ACTIVE if index == 0 else ChangeStageStatus.PENDING,
                entered_at=now if index == 0 else None,
            )
            for index, stage in enumerate(stages)
        ]
    )
    session.add(ChangeTransition(request_id=request.id, from_stage_id=None, to_stage_id=stages[0].id, from_status=None, to_status=ChangeStatus.OPEN, performed_by=actor.id, comment="Solicitud registrada", occurred_at=now))
    event = record_audit(session, user_id=actor.id, action="CREATE", entity_type="CHANGE_REQUEST", entity_id=request.id, after_data={"code": code, "title": request.title})
    event.occurred_at = now
    session.flush()
    _commit_with_kpis(session, project)
    return ok({"id": request.id, "code": code})


class ChangeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=3, max_length=300)
    description: str | None = Field(default=None, min_length=3, max_length=4000)
    justification: str | None = Field(default=None, max_length=4000)
    change_type: ChangeType | None = None
    priority: ChangePriority | None = None
    requester_area: str | None = Field(default=None, max_length=160)
    responsible_id: uuid.UUID | None = None


@router.patch("/change-requests/{request_id}")
def update_change(request_id: uuid.UUID, payload: ChangeUpdate, session: Session = Depends(get_db), actor: Manager = None) -> dict[str, Any]:
    request = session.get(ChangeRequest, request_id)
    if request is None:
        raise ApiError("NOT_FOUND", "Solicitud no encontrada", 404)
    data = payload.model_dump(exclude_unset=True)
    previous = {key: getattr(request, key) for key in data}
    for key, value in data.items():
        setattr(request, key, value)
    record_audit(session, user_id=actor.id, action="UPDATE", entity_type="CHANGE_REQUEST", entity_id=request.id, before_data=json_value(previous), after_data=json_value(data))
    session.commit()
    return ok({"id": request.id})


class FlowCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    comment: str | None = Field(default=None, max_length=2000)


class DecisionCommand(FlowCommand):
    approve: bool


class ProposalItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str = Field(min_length=1, max_length=80)
    duration_days: int | None = Field(default=None, ge=1, le=2000)
    start: date | None = None
    resources: list[dict[str, Any]] = Field(default_factory=list)
    note: str | None = Field(default=None, max_length=500)


class ProposalCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    updates: list[ProposalItem] = Field(default_factory=list)


def _flow(session: Session, request_id: uuid.UUID, actor: User) -> tuple[ChangeFlow, Project]:
    request = session.get(ChangeRequest, request_id)
    if request is None:
        raise ApiError("NOT_FOUND", "Solicitud no encontrada", 404)
    return ChangeFlow(session, request, actor.id), require_project(session, request.project_id)


def _flow_error(session: Session, error: Exception) -> ApiError:
    session.rollback()
    return ApiError("INVALID_CHANGE_FLOW", str(error), 409)


@router.post("/change-requests/{request_id}/advance")
def advance_change(request_id: uuid.UUID, payload: FlowCommand, session: Session = Depends(get_db), actor: Manager = None) -> dict[str, Any]:
    flow, project = _flow(session, request_id, actor)
    try:
        flow.advance(payload.comment)
    except ChangeFlowError as error:
        raise _flow_error(session, error) from error
    _commit_with_kpis(session, project)
    return ok({"status": flow.request.status.value})


@router.post("/change-requests/{request_id}/decision")
def decide_change(request_id: uuid.UUID, payload: DecisionCommand, session: Session = Depends(get_db), actor: Manager = None) -> dict[str, Any]:
    flow, project = _flow(session, request_id, actor)
    try:
        flow.decide(payload.approve, payload.comment)
    except ChangeFlowError as error:
        raise _flow_error(session, error) from error
    _commit_with_kpis(session, project)
    return ok({"status": flow.request.status.value})


@router.put("/change-requests/{request_id}/proposal")
def save_proposal(request_id: uuid.UUID, payload: ProposalCommand, session: Session = Depends(get_db), actor: Manager = None) -> dict[str, Any]:
    flow, _ = _flow(session, request_id, actor)
    updates = [item.model_dump(exclude_none=True) for item in payload.updates]
    try:
        flow.save_proposal(updates)
    except ChangeFlowError as error:
        raise _flow_error(session, error) from error
    session.commit()
    return ok({"proposal": updates})


@router.post("/change-requests/{request_id}/simulate")
def simulate_change(request_id: uuid.UUID, session: Session = Depends(get_db), actor: Manager = None) -> dict[str, Any]:
    flow, project = _flow(session, request_id, actor)
    try:
        result = flow.simulate()
    except (ChangeFlowError, ScheduleError) as error:
        raise _flow_error(session, error) from error
    _commit_with_kpis(session, project)
    return ok(result)


@router.post("/change-requests/{request_id}/apply-v2")
def apply_change_v2(request_id: uuid.UUID, session: Session = Depends(get_db), actor: Manager = None) -> dict[str, Any]:
    flow, project = _flow(session, request_id, actor)
    try:
        result = flow.apply()
    except (ChangeFlowError, ScheduleError) as error:
        raise _flow_error(session, error) from error
    session.commit()
    return ok(result)


# ========================================================= dashboards
def _month_points(start: date, finish: date) -> list[date]:
    points = []
    current = date(start.year, start.month, 1)
    while current <= finish:
        nxt = date(current.year + (current.month // 12), current.month % 12 + 1, 1)
        points.append(min(nxt - timedelta(days=1), finish))
        current = nxt
    return points


@router.get("/projects/{project_id}/dashboard/project")
def dashboard_project(
    project_id: uuid.UUID, stage: str | None = None, session: Session = Depends(get_db), _: CurrentUser = None
) -> dict[str, Any]:
    project = require_project(session, project_id)
    analytics = ProjectAnalytics(session, project)
    metrics = analytics.metrics()
    finish = analytics.project_finish()
    stages = [state for state, level in ordered_states(analytics) if state.kind == "ETAPA"]
    stage_rows = [
        {
            "external_id": state.external_id,
            "name": state.name,
            "planned_pct": state.planned_pct * HUNDRED,
            "progress": state.progress_pct,
            "planned_cost": state.planned_cost,
            "actual_cost": state.actual_cost,
            "status": state.status,
            "forecast_finish": state.forecast_finish,
            "baseline_finish": state.baseline_finish,
        }
        for state in stages
    ]

    def in_stage(state: ElementState) -> bool:
        if not stage:
            return True
        cursor = state
        while cursor.parent_external_id:
            cursor = analytics.states[cursor.parent_external_id]
        return cursor.external_id == stage

    leaves = [state for state in analytics.leaves() if in_stage(state)]
    late = [
        {
            "external_id": state.external_id,
            "name": state.name,
            "planned_pct": state.planned_pct * HUNDRED,
            "progress": state.progress_pct,
            "forecast_finish": state.forecast_finish,
            "baseline_finish": state.baseline_finish,
            "slip_days": state.slip_days,
            "is_critical": state.is_critical,
            "status": state.status,
            "status_label": STATUS_LABELS.get(state.status),
        }
        for state in sorted(leaves, key=lambda item: (item.status != "ATRASADA", not item.is_critical, item.forecast_start or date.max))
        if state.kind == "SUBACTIVIDAD" and (state.status == "ATRASADA" or (state.slip_days > 0 and state.progress_pct < HUNDRED and state.is_critical))
    ][:10]
    points = []
    if finish["start"] and finish["baseline"]:
        for point in _month_points(finish["start"], max(finish["baseline"], finish["forecast"] or finish["baseline"])):
            evm = analytics.evm(point)
            row = {"date": point, "pv": evm["PV"]}
            if point <= analytics.cutoff:
                row.update({"ev": evm["EV"], "ac": evm["AC"]})
            points.append(row)
        cutoff_evm = analytics.evm()
        points.append({"date": analytics.cutoff, "pv": cutoff_evm["PV"], "ev": cutoff_evm["EV"], "ac": cutoff_evm["AC"], "cutoff": True})
        points.sort(key=lambda item: item["date"])
    milestone_rows = [
        {"external_id": m.external_id, "name": m.name, "baseline": m.baseline_finish or m.finish, "forecast": m.forecast_finish, "status": m.status, "progress": m.progress_pct}
        for m in analytics.milestones()
    ]
    overview = resources_overview(project_id, session, None)["data"]
    overallocated = overview["overallocations"]
    load_summary = sorted(
        (
            {"name": row["name"], "peak_pct": row["peak_pct"], "hours": row["total_hours"], "tasks": row["task_count"]}
            for row in overview["resources"]
            if row["type"] == "HUMANO"
        ),
        key=lambda item: -item["peak_pct"],
    )
    reserve = (
        analytics.calendar.working_days_between(finish["forecast"], project.committed_finish)
        if finish["forecast"] and project.committed_finish
        else None
    )
    alerts = []
    critical_late = [row for row in late if row["is_critical"]]
    for row in critical_late[:3]:
        finish_text = _dmy(row["forecast_finish"])
        if row["status"] == "ATRASADA":
            text = f"{row['external_id']} (ruta crítica) lleva {float(row['progress']):.0f} % contra {float(row['planned_pct']):.0f} % planificado; terminaría el {finish_text}."
        else:
            text = f"{row['external_id']} (ruta crítica) se desplaza {row['slip_days']} días hábiles; terminaría el {finish_text}."
        alerts.append({"level": "crit" if row["status"] == "ATRASADA" else "warn", "text": text})
    for row in [row for row in late if not row["is_critical"]][:3]:
        alerts.append({"level": "warn", "text": f"{row['external_id']} atrasada: {float(row['progress']):.0f} % real vs {float(row['planned_pct']):.0f} % plan."})
    for row in overallocated[:2]:
        alerts.append({"level": "warn", "text": f"Sobreasignación de {row['resource']}: {float(row['peak_pct']):.0f} % ({row['days']} días desde el {_dmy(row['from'])})."})
    if reserve is not None:
        alerts.append({"level": "info" if reserve >= 0 else "crit", "text": f"Reserva hasta la fecha comprometida: {reserve} días hábiles."})
    kpi_values = {}
    for kpi in session.scalars(sa.select(Kpi).where(Kpi.project_id == project_id, Kpi.category == "PROYECTO")).all():
        value, _ = evaluate(kpi.formula, metrics, variable_codes(session, project_id))
        kpi_values[kpi.code] = {"name": kpi.name, "value": value, "status": kpi_status(value, kpi.green_threshold, kpi.yellow_threshold), "unit": kpi.unit}
    return ok(
        {
            "cutoff": analytics.cutoff,
            "project": {"name": project.name, "code": project.code, "committed_finish": project.committed_finish, "budget": project.budget},
            "metrics": {key: metrics[key] for key in ("BAC", "PV", "EV", "AC", "SPI", "CPI", "SV", "CV", "EAC", "VAC", "AVANCE_REAL", "AVANCE_PLAN", "MILESTONES_ON_TIME_PCT", "CLOSING_MILESTONE_DEVIATION", "LATE_ACTIVITIES_PCT")},
            "finish": finish,
            "reserve_days": reserve,
            "late_count": sum(1 for state in leaves if state.status == "ATRASADA"),
            "milestones_done": sum(1 for m in analytics.milestones() if m.progress_pct >= HUNDRED),
            "milestones_total": len(analytics.milestones()),
            "stages": stage_rows,
            "curve": points,
            "late": late,
            "milestones": milestone_rows,
            "load": load_summary,
            "overallocations": overallocated,
            "alerts": alerts,
            "kpis": kpi_values,
        }
    )


@router.get("/projects/{project_id}/dashboard/change")
def dashboard_change(
    project_id: uuid.UUID, change_type: str | None = None, session: Session = Depends(get_db), _: CurrentUser = None
) -> dict[str, Any]:
    project = require_project(session, project_id)
    analytics = ProjectAnalytics(session, project)
    metrics = analytics.metrics()
    board = change_board(project_id, session, None)["data"]
    requests = [row for row in board["requests"] if not change_type or row["type"] == change_type]
    stages = board["stages"]
    funnel = []
    for stage in stages:
        funnel.append(
            {
                "sequence": stage["sequence"],
                "name": stage["name"],
                "count": sum(1 for row in requests if row["stage_sequence"] == stage["sequence"] and row["status"] in {"ABIERTA", "APROBADA"}),
            }
        )
    durations: dict[int, list[float]] = defaultdict(list)
    request_ids = [row["id"] for row in requests]
    if request_ids:
        rows = session.execute(
            sa.select(ChangeRequestStage, ChangeStage)
            .join(ChangeStage, ChangeRequestStage.stage_id == ChangeStage.id)
            .where(ChangeRequestStage.request_id.in_(request_ids), ChangeRequestStage.entered_at.is_not(None), ChangeRequestStage.exited_at.is_not(None))
        ).all()
        for record, stage in rows:
            durations[stage.sequence].append((record.exited_at - record.entered_at).total_seconds() / 86400)
    stage_times = [
        {"sequence": stage["sequence"], "name": stage["name"], "avg_days": (sum(durations[stage["sequence"]]) / len(durations[stage["sequence"]])) if durations[stage["sequence"]] else None, "sla_days": (stage["sla_hours"] or 0) / 24}
        for stage in stages
    ]
    by_status: dict[str, int] = defaultdict(int)
    by_type: dict[str, int] = defaultdict(int)
    for row in requests:
        by_status[row["status_label"]] += 1
        by_type[row["type_label"]] += 1
    risk = []
    for row in requests:
        days = row["delta_days"] or 0
        cost = float(row["delta_cost"] or 0)
        impact = "ALTO" if days >= 4 or cost >= 2_000_000 else "MEDIO" if days > 0 or cost >= 500_000 else "BAJO"
        detail = change_detail(row["id"], session, None)["data"]
        critical = bool(detail["preview"] and not detail["preview"].get("error") and detail["preview"].get("critical_affected")) or any(
            item.get("critical") for impact_row in detail["impacts"][:1] for item in (impact_row["affected"] or [])
        )
        probability = "ALTA" if critical else "MEDIA" if days > 0 else "BAJA"
        risk.append({"code": row["code"], "title": row["title"], "impact": impact, "probability": probability, "status": row["status"]})
    alerts = []
    for row in requests:
        if row["sla_breached"]:
            alerts.append({"level": "crit", "text": f"{row['code']} superó el SLA de la etapa «{row['stage_name']}»."})
        if row["evidences"] == 0 and row["status"] in {"ABIERTA", "APROBADA"}:
            alerts.append({"level": "warn", "text": f"{row['code']} no tiene evidencias adjuntas."})
        if row["status"] == "APROBADA" and not row["applied"]:
            alerts.append({"level": "info", "text": f"{row['code']} está aprobada y pendiente de aplicar al plan."})
    for item in risk:
        if item["probability"] == "ALTA" and item["status"] in {"ABIERTA", "APROBADA"}:
            alerts.append({"level": "warn", "text": f"{item['code']} afecta la ruta crítica."})
    manual = {row.code: row.value for row in session.scalars(sa.select(ManualMetric).where(ManualMetric.project_id == project_id)).all()}
    kpi_values = {}
    for kpi in session.scalars(sa.select(Kpi).where(Kpi.project_id == project_id, Kpi.category == "CAMBIO").order_by(Kpi.code)).all():
        value, _ = evaluate(kpi.formula, metrics, variable_codes(session, project_id))
        kpi_values[kpi.code] = {"name": kpi.name, "value": value, "status": kpi_status(value, kpi.green_threshold, kpi.yellow_threshold), "unit": kpi.unit, "is_additional": kpi.is_additional}
    return ok(
        {
            "cutoff": analytics.cutoff,
            "requests": requests,
            "funnel": funnel,
            "stage_times": stage_times,
            "by_status": dict(by_status),
            "by_type": dict(by_type),
            "risk": risk,
            "alerts": alerts,
            "metrics": {key: metrics[key] for key in metrics if key.startswith("CHANGE_")},
            "contingency_amount": analytics.contingency_amount(),
            "manual": {key: manual.get(key, ZERO) for key in MANUAL_METRICS},
            "kpis": kpi_values,
        }
    )


# =========================================================== checklist
@router.get("/projects/{project_id}/checklist")
def checklist(project_id: uuid.UUID, session: Session = Depends(get_db), _: CurrentUser = None) -> dict[str, Any]:
    project = require_project(session, project_id)
    counts = defaultdict(int)
    for kind in session.scalars(sa.select(GanttElement.element_type).where(GanttElement.project_id == project_id)).all():
        counts[kind.value] += 1
    dependency_types = sorted({row.value for row in session.scalars(sa.select(Dependency.dependency_type).where(Dependency.project_id == project_id)).all()})
    humans = session.scalar(sa.select(sa.func.count(Resource.id)).where(Resource.project_id == project_id, Resource.resource_type == ResourceType.HUMAN)) or 0
    resource_types = sorted({row.value for row in session.scalars(sa.select(Resource.resource_type).where(Resource.project_id == project_id)).all()})
    kpi_project = session.scalar(sa.select(sa.func.count(Kpi.id)).where(Kpi.project_id == project_id, Kpi.category == "PROYECTO")) or 0
    kpi_change = session.scalar(sa.select(sa.func.count(Kpi.id)).where(Kpi.project_id == project_id, Kpi.category == "CAMBIO")) or 0
    changes = session.scalar(sa.select(sa.func.count(ChangeRequest.id)).where(ChangeRequest.project_id == project_id)) or 0
    roles = session.scalar(sa.text("SELECT count(*) FROM roles")) or 0
    items = [
        ("Etapas", counts["ETAPA"], 4),
        ("Actividades", counts["ACTIVIDAD"], 12),
        ("Subactividades", counts["SUBACTIVIDAD"], 20),
        ("Tipos de dependencia", len(dependency_types), 4),
        ("Profesionales", humans, 5),
        ("Tipos de recursos", len(resource_types), 4),
        ("Hitos", counts["HITO"], 6),
        ("KPI de proyecto e hitos", kpi_project, 8),
        ("Solicitudes de cambio", changes, 5),
        ("KPI de gestión del cambio", kpi_change, 12),
        ("Tableros de comando", 2, 2),
        ("Roles", roles, 2),
    ]
    return ok(
        {
            "project": project.name,
            "items": [{"label": label, "value": value, "required": required, "ok": value >= required} for label, value, required in items],
            "dependency_types": dependency_types,
            "resource_types": resource_types,
        }
    )


def _dmy(value: Any) -> str:
    """Format a date (or ISO date string) as dd-mm-aaaa for user-facing text."""

    if not value:
        return "—"
    if isinstance(value, str):
        value = date.fromisoformat(value[:10])
    return value.strftime("%d-%m-%Y")
