"""Ten-stage change-control workflow used by the web application.

Lifecycle (stage names are configurable, the roles of the stages are not):

1-5  Registro → Revisión inicial → Clasificación → Análisis de impacto → Comité
6    Decisión: approve (status APROBADA) or reject (status RECHAZADA, closed)
7    Planificación del cambio: the proposal can still be adjusted/simulated
8    Implementación: *apply* writes the proposal to the plan, recalculates the
     schedule, costs and KPIs and seals baseline vN+1
9    Verificación
10   Cierre y línea base: advancing closes the request (status CERRADA)

A proposal is a list of task updates:
``{"task_id": "A26", "duration_days": 20, "resources": [{"resource": "BI1", "hours": 32}]}``
``resources`` adds hours (human) or quantity (non-human) to the task assignment.
"""

from __future__ import annotations

import copy
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.domain.models import Assignment as DomainAssignment
from app.domain.models import Task
from app.models import (
    Assignment,
    ChangeImpact,
    ChangeRequest,
    ChangeRequestStage,
    ChangeStage,
    ChangeStageStatus,
    ChangeStatus,
    ChangeTransition,
    GanttElement,
    Project,
    Resource,
    ResourceType,
)
from app.services.analytics import ProjectAnalytics, json_value, project_clock
from app.services.calculation_engine import DeterministicCalculationEngine
from app.services.f7 import DEFAULT_CHANGE_STAGES
from app.services.kpi_engine import recalculate_kpis
from app.services.persistence import _domain_tasks, create_baseline, project_calendar, recalculate_project

ZERO = Decimal("0")


class ChangeFlowError(ValueError):
    """Invalid workflow operation (mapped to HTTP 400/409)."""


@dataclass
class StageRef:
    record: ChangeRequestStage
    stage: ChangeStage


def ensure_stages(session: Session, project_id: uuid.UUID) -> list[ChangeStage]:
    stages = list(
        session.scalars(
            sa.select(ChangeStage)
            .where(ChangeStage.project_id == project_id, ChangeStage.is_active.is_(True))
            .order_by(ChangeStage.sequence)
        ).all()
    )
    if stages:
        return stages
    stages = [
        ChangeStage(project_id=project_id, name=item.name, sequence=item.sequence, sla_hours=item.sla_hours, is_active=True)
        for item in DEFAULT_CHANGE_STAGES
    ]
    session.add_all(stages)
    session.flush()
    return stages


def _is_decision(stage: ChangeStage) -> bool:
    return "decisi" in stage.name.casefold() or stage.sequence == 6


def _is_implementation(stage: ChangeStage) -> bool:
    return "implementa" in stage.name.casefold() or stage.sequence == 8


class ChangeFlow:
    def __init__(self, session: Session, request: ChangeRequest, actor_id: uuid.UUID | None) -> None:
        self.session = session
        self.request = request
        self.actor_id = actor_id
        self.project = session.get(Project, request.project_id)

    # ----------------------------------------------------------- helpers
    def stages(self) -> list[StageRef]:
        rows = self.session.execute(
            sa.select(ChangeRequestStage, ChangeStage)
            .join(ChangeStage, ChangeRequestStage.stage_id == ChangeStage.id)
            .where(ChangeRequestStage.request_id == self.request.id)
            .order_by(ChangeStage.sequence)
        ).all()
        return [StageRef(record, stage) for record, stage in rows]

    def active(self) -> StageRef | None:
        return next((item for item in self.stages() if item.record.status == ChangeStageStatus.ACTIVE), None)

    def _move(self, current: StageRef, comment: str | None, now: datetime, from_status: ChangeStatus | None = None) -> StageRef | None:
        current.record.status = ChangeStageStatus.COMPLETED
        current.record.exited_at = now
        current.record.completed_by = self.actor_id
        current.record.notes = comment
        following = [item for item in self.stages() if item.stage.sequence > current.stage.sequence]
        if not following:
            self.request.current_stage_id = current.stage.id
            return None
        nxt = following[0]
        nxt.record.status = ChangeStageStatus.ACTIVE
        nxt.record.entered_at = now
        self.request.current_stage_id = nxt.stage.id
        self.session.add(
            ChangeTransition(
                request_id=self.request.id,
                from_stage_id=current.stage.id,
                to_stage_id=nxt.stage.id,
                from_status=from_status or self.request.status,
                to_status=self.request.status,
                performed_by=self.actor_id,
                comment=comment,
                occurred_at=now,
            )
        )
        return nxt

    def _audit(self, action: str, after: dict[str, Any]) -> None:
        event = record_audit(
            self.session,
            user_id=self.actor_id,
            action=action,
            entity_type="CHANGE_REQUEST",
            entity_id=self.request.id,
            after_data=json_value(after),
        )
        event.occurred_at = project_clock(self.project)

    # ------------------------------------------------------------ actions
    def advance(self, comment: str | None = None, now: datetime | None = None) -> ChangeRequest:
        now = now or project_clock(self.project)
        if self.request.status in {ChangeStatus.REJECTED, ChangeStatus.CANCELLED, ChangeStatus.CLOSED}:
            raise ChangeFlowError("La solicitud ya está cerrada")
        current = self.active()
        if current is None:
            raise ChangeFlowError("La solicitud no tiene una etapa activa")
        if _is_decision(current.stage):
            raise ChangeFlowError("En la etapa de Decisión debe aprobar o rechazar la solicitud")
        if _is_implementation(current.stage) and not self._applied():
            raise ChangeFlowError("Aplique el cambio al plan antes de pasar a Verificación")
        nxt = self._move(current, comment, now)
        if nxt is None:
            self.request.status = ChangeStatus.CLOSED
            self.request.closed_at = now
            self.session.add(
                ChangeTransition(
                    request_id=self.request.id,
                    from_stage_id=current.stage.id,
                    to_stage_id=None,
                    from_status=ChangeStatus.APPROVED,
                    to_status=ChangeStatus.CLOSED,
                    performed_by=self.actor_id,
                    comment=comment,
                    occurred_at=now,
                )
            )
        self._audit("ADVANCE", {"to_stage": nxt.stage.name if nxt else "CERRADA", "comment": comment})
        self.session.flush()
        return self.request

    def decide(self, approve: bool, comment: str | None = None, now: datetime | None = None) -> ChangeRequest:
        now = now or project_clock(self.project)
        if self.request.status != ChangeStatus.OPEN:
            raise ChangeFlowError("Solo se decide una solicitud abierta")
        current = self.active()
        if current is None:
            raise ChangeFlowError("La solicitud no tiene una etapa activa")
        if approve and not _is_decision(current.stage):
            raise ChangeFlowError("La aprobación se registra en la etapa de Decisión")
        previous = self.request.status
        self.request.decided_at = now
        if approve:
            self.request.status = ChangeStatus.APPROVED
            self._move(current, comment, now, from_status=previous)
            self._audit("DECIDE", {"status": self.request.status.value, "comment": comment})
            self.session.flush()
            return self.request
        else:
            self.request.status = ChangeStatus.REJECTED
            self.request.closed_at = now
            current.record.status = ChangeStageStatus.COMPLETED
            current.record.exited_at = now
            current.record.completed_by = self.actor_id
            current.record.notes = comment
            for item in self.stages():
                if item.stage.sequence > current.stage.sequence:
                    item.record.status = ChangeStageStatus.SKIPPED
        self.session.add(
            ChangeTransition(
                request_id=self.request.id,
                from_stage_id=current.stage.id,
                to_stage_id=self.request.current_stage_id if approve else None,
                from_status=previous,
                to_status=self.request.status,
                performed_by=self.actor_id,
                comment=comment,
                occurred_at=now,
            )
        )
        self._audit("DECIDE", {"status": self.request.status.value, "comment": comment})
        self.session.flush()
        return self.request

    def save_proposal(self, updates: list[dict[str, Any]]) -> ChangeRequest:
        if self.request.status not in {ChangeStatus.OPEN, ChangeStatus.APPROVED}:
            raise ChangeFlowError("La propuesta solo se edita en solicitudes abiertas o aprobadas")
        if self._applied():
            raise ChangeFlowError("El cambio ya fue aplicado al plan")
        self._validate_updates(updates)
        self.request.proposal = json_value(updates)
        self._audit("PROPOSAL", {"updates": updates})
        self.session.flush()
        return self.request

    def simulate(self, updates: list[dict[str, Any]] | None = None, now: datetime | None = None) -> dict[str, Any]:
        proposal = updates if updates is not None else list(self.request.proposal or [])
        if not proposal:
            raise ChangeFlowError("La solicitud no tiene una propuesta de cambio para simular")
        self._validate_updates(proposal)
        result = simulate_proposal(self.session, self.project, proposal)
        impact = ChangeImpact(
            request_id=self.request.id,
            baseline_id=result["baseline_id"],
            proposed_project_finish=result["proposed_finish"],
            delta_schedule_days=result["delta_schedule_days"],
            delta_cost=result["delta_cost"],
            delta_contingency=result["delta_contingency"],
            affected_elements=json_value(result["affected"]),
            resource_effect=json_value(result["resources"]),
            summary=result["summary"],
        )
        impact.simulated_at = now or project_clock(self.project)
        self.session.add(impact)
        self._audit("SIMULATE_IMPACT", {"delta_days": result["delta_schedule_days"], "delta_cost": result["delta_cost"]})
        self.session.flush()
        return result

    def apply(self, now: datetime | None = None) -> dict[str, Any]:
        now = now or project_clock(self.project)
        if self.request.status != ChangeStatus.APPROVED:
            raise ChangeFlowError("Solo se puede aplicar una solicitud aprobada")
        if self._applied():
            raise ChangeFlowError("El cambio ya fue aplicado")
        proposal = list(self.request.proposal or [])
        if not proposal:
            raise ChangeFlowError("Defina la propuesta del cambio antes de aplicarla")
        before = ProjectAnalytics(self.session, self.project)
        finish_before = before.project_finish()
        impact = self.simulate(proposal, now=now)
        apply_proposal(self.session, self.project, proposal)
        recalculate_project(self.session, self.project)
        baseline = create_baseline(self.session, self.project, self.actor_id)
        self.session.flush()
        analytics = ProjectAnalytics(self.session, self.project)
        kpis = recalculate_kpis(self.session, self.project, analytics=analytics)
        current = self.active()
        while current is not None and current.stage.sequence < 8 and not _is_implementation(current.stage):
            current = self._move(current, "Cambio aplicado al plan", now)
        if current is not None and _is_implementation(current.stage):
            current.record.notes = f"Aplicado: línea base {baseline.version}"
            self._move(current, f"Aplicado: línea base {baseline.version}", now)
        self._audit("APPLY", {"baseline": baseline.version, "kpis": len(kpis)})
        self.session.flush()
        return {
            "baseline_version": baseline.version,
            "baseline_id": str(baseline.id),
            "impact": impact,
            "finish_before": finish_before,
            "finish_after": analytics.project_finish(),
            "kpis_recalculated": len(kpis),
        }

    def _applied(self) -> bool:
        return bool(
            self.session.scalar(
                sa.select(sa.func.count())
                .select_from(ChangeRequestStage)
                .join(ChangeStage, ChangeRequestStage.stage_id == ChangeStage.id)
                .where(
                    ChangeRequestStage.request_id == self.request.id,
                    ChangeRequestStage.status == ChangeStageStatus.COMPLETED,
                    ChangeRequestStage.notes.like("Aplicado:%"),
                )
            )
        )

    def applied(self) -> bool:
        return self._applied()

    def _validate_updates(self, updates: Iterable[dict[str, Any]]) -> None:
        known = {
            element.external_id: element
            for element in self.session.scalars(
                sa.select(GanttElement).where(GanttElement.project_id == self.request.project_id)
            ).all()
        }
        resources = {
            resource.external_id
            for resource in self.session.scalars(
                sa.select(Resource).where(Resource.project_id == self.request.project_id)
            ).all()
        }
        for update in updates:
            task_id = str(update.get("task_id", ""))
            element = known.get(task_id)
            if element is None:
                raise ChangeFlowError(f"Elemento inexistente en la propuesta: {task_id}")
            if element.element_type.value != "SUBACTIVIDAD" and (update.get("duration_days") or update.get("resources")):
                raise ChangeFlowError(f"Solo las subactividades aceptan duración o recursos: {task_id}")
            duration = update.get("duration_days")
            if duration is not None and int(duration) <= 0:
                raise ChangeFlowError("La duración propuesta debe ser mayor que cero")
            for item in update.get("resources", []) or []:
                if str(item.get("resource")) not in resources:
                    raise ChangeFlowError(f"Recurso inexistente en la propuesta: {item.get('resource')}")


def _proposal_inputs(
    session: Session, project: Project, updates: list[dict[str, Any]]
) -> tuple[list[Task], list[Any], list[DomainAssignment], list[Task], list[DomainAssignment]]:
    tasks, resources, assignments = _domain_tasks(session, project)
    resource_ids = {
        row.external_id: (str(row.id), row.resource_type)
        for row in session.scalars(sa.select(Resource).where(Resource.project_id == project.id)).all()
    }
    proposal_tasks = copy.deepcopy(tasks)
    proposal_assignments = copy.deepcopy(assignments)
    by_task = {task.task_id: task for task in proposal_tasks}
    for update in updates:
        task = by_task[str(update["task_id"])]
        if update.get("duration_days") is not None:
            task.duration_days = int(update["duration_days"])
            task.effort_hours = None
        if update.get("start"):
            task.start = date.fromisoformat(str(update["start"]))
        for item in update.get("resources", []) or []:
            resource_id, kind = resource_ids[str(item["resource"])]
            amount = Decimal(str(item.get("hours") or item.get("quantity") or 0))
            existing = next(
                (a for a in proposal_assignments if a.task_id == task.task_id and a.resource_id == resource_id), None
            )
            if existing is None:
                existing = DomainAssignment(task.task_id, resource_id, hours_per_day=Decimal(str(item.get("h_dia") or 0)))
                proposal_assignments.append(existing)
            if kind == ResourceType.HUMAN:
                existing.planned_hours += amount
            else:
                existing.quantity += amount
    return tasks, resources, assignments, proposal_tasks, proposal_assignments


def simulate_proposal(session: Session, project: Project, updates: list[dict[str, Any]]) -> dict[str, Any]:
    """What-if on a deep copy of the current plan; nothing is persisted."""

    from app.models import Baseline, BaselineStatus

    engine = DeterministicCalculationEngine(project_calendar(session, project))
    tasks, resources, assignments, proposal_tasks, proposal_assignments = _proposal_inputs(session, project, updates)

    def run(task_list: list[Task], assignment_list: list[DomainAssignment]) -> tuple[Any, Any]:
        leaves = [task for task in task_list if task.kind in {"SUBACTIVIDAD", "HITO"}]
        schedule = engine.schedule(leaves, project.planned_start, None)
        merged = copy.deepcopy(task_list)
        for task in merged:
            calculated = schedule.tasks.get(task.task_id)
            if calculated is not None:
                task.start, task.finish, task.duration_days = calculated.start, calculated.finish, calculated.duration_days
                task.critical = calculated.critical
        costs = engine.calculate_costs(merged, resources, assignment_list)
        return schedule, costs

    base_schedule, base_costs = run(tasks, assignments)
    new_schedule, new_costs = run(proposal_tasks, proposal_assignments)
    calendar = engine.scheduler.calendar
    delta_days = calendar.working_days_between(base_schedule.project_finish, new_schedule.project_finish)
    delta_cost = new_costs.project.planned_cost - base_costs.project.planned_cost
    affected: list[dict[str, Any]] = []
    names = {task.task_id: task.name for task in tasks}
    for task_id, task in new_schedule.tasks.items():
        before = base_schedule.tasks[task_id]
        cost_before = base_costs.by_task[task_id].planned_cost
        cost_after = new_costs.by_task[task_id].planned_cost
        if before.start != task.start or before.finish != task.finish or cost_before != cost_after or before.duration_days != task.duration_days:
            affected.append(
                {
                    "task_id": task_id,
                    "name": names.get(task_id, task_id),
                    "start_before": before.start,
                    "start_after": task.start,
                    "finish_before": before.finish,
                    "finish_after": task.finish,
                    "duration_before": before.duration_days,
                    "duration_after": task.duration_days,
                    "cost_before": cost_before,
                    "cost_after": cost_after,
                    "critical": task.critical,
                }
            )
    affected.sort(key=lambda item: (item["start_after"] or date.max, item["task_id"]))
    resource_names = {resource.resource_id: resource.name for resource in resources}
    hours_before: dict[str, Decimal] = {}
    hours_after: dict[str, Decimal] = {}
    for item in assignments:
        hours_before[item.resource_id] = hours_before.get(item.resource_id, ZERO) + item.planned_hours + item.quantity
    for item in proposal_assignments:
        hours_after[item.resource_id] = hours_after.get(item.resource_id, ZERO) + item.planned_hours + item.quantity
    resources_effect = [
        {
            "resource": resource_names.get(resource_id, resource_id),
            "before": hours_before.get(resource_id, ZERO),
            "after": hours_after.get(resource_id, ZERO),
            "delta": hours_after.get(resource_id, ZERO) - hours_before.get(resource_id, ZERO),
        }
        for resource_id in sorted(set(hours_before) | set(hours_after))
        if hours_after.get(resource_id, ZERO) != hours_before.get(resource_id, ZERO)
    ]
    analytics = ProjectAnalytics(session, project)
    contingency = analytics.contingency_amount()
    committed = project.committed_finish
    baseline = session.scalar(
        sa.select(Baseline).where(Baseline.project_id == project.id, Baseline.status == BaselineStatus.ACTIVE)
    )
    reserve_before = calendar.working_days_between(base_schedule.project_finish, committed) if committed else None
    reserve_after = calendar.working_days_between(new_schedule.project_finish, committed) if committed else None
    return {
        "baseline_id": baseline.id if baseline else None,
        "baseline_version": baseline.version if baseline else None,
        "baseline_finish": base_schedule.project_finish,
        "proposed_finish": new_schedule.project_finish,
        "baseline_cost": base_costs.project.planned_cost,
        "proposed_cost": new_costs.project.planned_cost,
        "delta_schedule_days": delta_days,
        "delta_cost": delta_cost,
        "contingency_amount": contingency,
        "delta_contingency": delta_cost,
        "contingency_consumption_pct": (delta_cost / contingency * 100) if contingency else ZERO,
        "reserve_before": reserve_before,
        "reserve_after": reserve_after,
        "affected": affected,
        "resources": resources_effect,
        "critical_affected": any(item["critical"] for item in affected),
        "summary": f"Plazo {delta_days:+d} días hábiles; costo {delta_cost:+,.0f} CLP".replace(",", "."),
    }


def apply_proposal(session: Session, project: Project, updates: list[dict[str, Any]]) -> None:
    """Write a validated proposal into the current plan rows."""

    elements = {
        element.external_id: element
        for element in session.scalars(sa.select(GanttElement).where(GanttElement.project_id == project.id)).all()
    }
    resources = {
        resource.external_id: resource
        for resource in session.scalars(sa.select(Resource).where(Resource.project_id == project.id)).all()
    }
    for update in updates:
        element = elements[str(update["task_id"])]
        if update.get("duration_days") is not None:
            element.duration_days = int(update["duration_days"])
            element.effort_hours = None
            element.planned_finish = None
        if update.get("start"):
            element.planned_start = date.fromisoformat(str(update["start"]))
        for item in update.get("resources", []) or []:
            resource = resources[str(item["resource"])]
            amount = Decimal(str(item.get("hours") or item.get("quantity") or 0))
            assignment = session.scalar(
                sa.select(Assignment).where(Assignment.element_id == element.id, Assignment.resource_id == resource.id)
            )
            if assignment is None:
                assignment = Assignment(
                    project_id=project.id,
                    element_id=element.id,
                    resource_id=resource.id,
                    hours_per_day=Decimal(str(item.get("h_dia") or 0)),
                )
                session.add(assignment)
            if resource.resource_type == ResourceType.HUMAN:
                assignment.planned_hours = (assignment.planned_hours or ZERO) + amount
            else:
                assignment.quantity = (assignment.quantity or ZERO) + amount
    session.flush()
