"""Milestones, change control and baseline operations (F7).

The module has two deliberately small layers.  ``ImpactAnalyzer`` is a pure
service and is therefore safe to use from a worker or an HTTP request.  The
SQLAlchemy backed ``ChangeControlService`` only coordinates persistence and
delegates all schedule and cost calculations to the existing deterministic
engine.
"""

from __future__ import annotations

import copy
import re
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from ..domain.models import Assignment as DomainAssignment
from ..domain.models import Dependency as DomainDependency
from ..domain.models import Resource as DomainResource
from ..domain.models import ResourceType as DomainResourceType
from ..domain.models import Task
from ..models import AcceptanceCriterion, Assignment as AssignmentRow, AuditLog
from ..models import Baseline, BaselineElement
from ..models import BaselineStatus, ChangeImpact, ChangeRequest, ChangeRequestStage
from ..models import ChangeStage, ChangeStageStatus, ChangeStatus, ChangeTransition
from ..models import CriterionStatus, Dependency, GanttElement, GanttElementType
from ..models import Evidence, Milestone, Project, Resource
from .calculation_engine import DeterministicCalculationEngine
from .costs import CostReport
from .persistence import project_calendar, recalculate_project


class F7Error(ValueError):
    """Base error for an invalid F7 operation."""


class NotFoundError(F7Error):
    """Raised when a requested project entity does not exist."""


class WorkflowError(F7Error):
    """Raised when a change request cannot advance in its workflow."""


@dataclass(frozen=True, slots=True)
class TaskUpdate:
    """A supported what-if change to one Gantt element.

    Dates are intentionally typed as ``date`` here.  The HTTP adapter parses
    ISO values before handing them to the domain service, keeping the engine
    free of transport concerns.
    """

    task_id: str
    start: date | None = None
    finish: date | None = None
    duration_days: int | None = None
    planned_cost: Decimal | None = None
    effort_hours: Decimal | None = None
    progress_pct: Decimal | None = None

    def values(self) -> dict[str, object]:
        """Return only fields explicitly supplied by the proposal."""

        return {
            key: value
            for key, value in {
                "start": self.start,
                "finish": self.finish,
                "duration_days": self.duration_days,
                "planned_cost": self.planned_cost,
                "effort_hours": self.effort_hours,
                "progress_pct": self.progress_pct,
            }.items()
            if value is not None
        }


@dataclass(frozen=True, slots=True)
class ImpactResult:
    """Deterministic result of simulating a proposal in an isolated copy."""

    baseline_finish: date
    proposed_finish: date
    baseline_cost: Decimal
    proposed_cost: Decimal
    contingency_reserve: Decimal
    delta_schedule_days: int
    delta_cost: Decimal
    delta_contingency: Decimal
    affected_elements: tuple[dict[str, object], ...]
    resource_effect: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        """Serialize the result without leaking engine implementation types."""

        return {
            "baseline_finish": self.baseline_finish.isoformat(),
            "proposed_finish": self.proposed_finish.isoformat(),
            "baseline_cost": str(self.baseline_cost),
            "proposed_cost": str(self.proposed_cost),
            "contingency_reserve": str(self.contingency_reserve),
            "delta_schedule_days": self.delta_schedule_days,
            "delta_cost": str(self.delta_cost),
            "delta_contingency": str(self.delta_contingency),
            "affected_elements": _json_safe(list(self.affected_elements)),
            "resource_effect": _json_safe(self.resource_effect),
        }


@dataclass(frozen=True, slots=True)
class BaselineComparison:
    """Field-level comparison between a baseline snapshot and a proposal."""

    baseline_version: str
    changes: tuple[dict[str, object], ...]

    def as_dict(self) -> dict[str, object]:
        """Return a transport-friendly comparison."""

        return {"baseline_version": self.baseline_version, "changes": list(self.changes)}


@dataclass(frozen=True, slots=True)
class StageDefinition:
    """Configurable change-control stage and its SLA."""

    name: str
    sequence: int
    sla_hours: int | None = None


DEFAULT_CHANGE_STAGES: tuple[StageDefinition, ...] = tuple(
    StageDefinition(name, sequence, 24 if sequence < 9 else 48)
    for sequence, name in enumerate(
        (
            "Registro",
            "Revisión inicial",
            "Clasificación y prioridad",
            "Análisis de impacto",
            "Revisión del comité",
            "Decisión",
            "Planificación del cambio",
            "Implementación",
            "Verificación",
            "Cierre y línea base",
        ),
        start=1,
    )
)


class ImpactAnalyzer:
    """Run what-if calculations on a deep copy of the planning graph."""

    def __init__(self, engine: DeterministicCalculationEngine) -> None:
        self.engine = engine

    def simulate(
        self,
        tasks: Iterable[Task],
        resources: Iterable[DomainResource],
        assignments: Iterable[DomainAssignment] = (),
        updates: Iterable[TaskUpdate] = (),
        *,
        project_start: date | None = None,
        project_deadline: date | None = None,
        contingency_pct: Decimal = Decimal("0"),
    ) -> ImpactResult:
        """Calculate schedule, cost and reserve deltas without mutating input."""

        original_tasks = tuple(copy.deepcopy(tuple(tasks)))
        original_resources = tuple(copy.deepcopy(tuple(resources)))
        original_assignments = tuple(copy.deepcopy(tuple(assignments)))
        proposal_updates = tuple(updates)
        baseline_schedule = self.engine.schedule(
            self._scheduleable_tasks(original_tasks),
            project_start=project_start,
            project_deadline=project_deadline,
        )
        baseline_all = tuple(copy.deepcopy(original_tasks))
        self._merge_schedule(baseline_all, baseline_schedule.tasks)
        baseline_cost_report = self.engine.calculate_costs(
            baseline_all, original_resources, original_assignments
        )
        proposal_tasks = tuple(copy.deepcopy(original_tasks))
        self._apply_updates(proposal_tasks, proposal_updates)
        proposal_schedule = self.engine.schedule(
            self._scheduleable_tasks(proposal_tasks),
            project_start=project_start,
            project_deadline=project_deadline,
        )
        self._merge_schedule(proposal_tasks, proposal_schedule.tasks)
        proposal_cost_report = self.engine.calculate_costs(
            proposal_tasks, original_resources, original_assignments
        )
        baseline_cost = baseline_cost_report.project.planned_cost
        proposed_cost = proposal_cost_report.project.planned_cost + self._explicit_cost_delta(
            proposal_cost_report, proposal_updates
        )
        delta_cost = proposed_cost - baseline_cost
        reserve_delta = delta_cost * Decimal(str(contingency_pct)) / Decimal("100")
        affected = self._affected_elements(
            {task.task_id: task for task in baseline_all},
            {task.task_id: task for task in proposal_tasks},
        )
        return ImpactResult(
            baseline_schedule.project_finish,
            proposal_schedule.project_finish,
            baseline_cost,
            proposed_cost,
            proposed_cost * Decimal(str(contingency_pct)) / Decimal("100"),
            self.engine.scheduler.calendar.working_days_between(
                baseline_schedule.project_finish, proposal_schedule.project_finish
            ),
            delta_cost,
            reserve_delta,
            tuple(affected),
            self._resource_effect(original_tasks, proposal_schedule.tasks, original_resources),
        )

    @staticmethod
    def _scheduleable_tasks(tasks: Iterable[Task]) -> tuple[Task, ...]:
        """Keep consolidation rows out of the schedule graph."""

        return tuple(task for task in tasks if task.kind in {"SUBACTIVIDAD", "HITO"})

    @staticmethod
    def _merge_schedule(tasks: Iterable[Task], scheduled: Mapping[str, Task]) -> None:
        """Copy calculated leaf values back to the hierarchy used by costs."""

        for task in tasks:
            calculated = scheduled.get(task.task_id)
            if calculated is None:
                continue
            task.start = calculated.start
            task.finish = calculated.finish
            task.duration_days = calculated.duration_days
            task.total_slack_days = calculated.total_slack_days
            task.free_slack_days = calculated.free_slack_days
            task.critical = calculated.critical

    @staticmethod
    def _apply_updates(tasks: tuple[Task, ...], updates: Iterable[TaskUpdate]) -> None:
        task_map = {task.task_id: task for task in tasks}
        for update in updates:
            task = task_map.get(update.task_id)
            if task is None:
                raise F7Error(f"Elemento inexistente en propuesta: {update.task_id}")
            for field_name, value in update.values().items():
                setattr(task, field_name, value)

    @staticmethod
    def _affected_elements(
        baseline: Mapping[str, Task], proposal: Mapping[str, Task]
    ) -> list[dict[str, object]]:
        affected: list[dict[str, object]] = []
        for task_id, task in proposal.items():
            before = baseline[task_id]
            fields = ("start", "finish", "duration_days", "planned_cost", "critical")
            differences = {
                field_name: {"before": getattr(before, field_name), "after": getattr(task, field_name)}
                for field_name in fields
                if getattr(before, field_name) != getattr(task, field_name)
            }
            if differences:
                affected.append({"task_id": task_id, "changes": differences})
        return affected

    @staticmethod
    def _resource_effect(
        baseline: Iterable[Task], proposal: Mapping[str, Task], resources: Iterable[DomainResource]
    ) -> dict[str, object]:
        baseline_hours = ImpactAnalyzer._hours_by_resource(baseline)
        proposed_hours = ImpactAnalyzer._hours_by_resource(proposal.values())
        resource_ids = {resource.resource_id for resource in resources}
        return {
            resource_id: {
                "before_hours": baseline_hours.get(resource_id, Decimal("0")),
                "after_hours": proposed_hours.get(resource_id, Decimal("0")),
                "delta_hours": proposed_hours.get(resource_id, Decimal("0"))
                - baseline_hours.get(resource_id, Decimal("0")),
            }
            for resource_id in resource_ids
            if baseline_hours.get(resource_id, Decimal("0"))
            != proposed_hours.get(resource_id, Decimal("0"))
        }

    @staticmethod
    def _explicit_cost_delta(report: CostReport, updates: Iterable[TaskUpdate]) -> Decimal:
        """Apply proposal cost overrides after the engine's assignment roll-up."""

        delta = Decimal("0")
        for update in updates:
            if update.planned_cost is not None and update.task_id in report.by_task:
                delta += update.planned_cost - report.by_task[update.task_id].planned_cost
        return delta

    @staticmethod
    def _hours_by_resource(tasks: Iterable[Task]) -> dict[str, Decimal]:
        totals: dict[str, Decimal] = {}
        for task in tasks:
            for assignment in task.assignments:
                totals[assignment.resource_id] = totals.get(assignment.resource_id, Decimal("0")) + (
                    assignment.planned_hours
                )
        return totals


class ChangeControlService:
    """Transactional coordinator for milestones, changes and baselines."""

    def __init__(self, session: Session, engine: DeterministicCalculationEngine) -> None:
        self.session = session
        self.engine = engine
        self.impact_analyzer = ImpactAnalyzer(engine)

    def configure_stages(
        self, project_id: uuid.UUID, definitions: Sequence[StageDefinition]
    ) -> list[ChangeStage]:
        """Replace active workflow stages, allowing at most ten ordered stages."""

        self._project(project_id)
        if len(definitions) != 10:
            raise F7Error("La configuración debe contener exactamente 10 etapas")
        sequences = [definition.sequence for definition in definitions]
        if sequences != list(range(1, len(definitions) + 1)):
            raise F7Error("Las etapas deben tener secuencia consecutiva desde 1")
        if any(not definition.name.strip() for definition in definitions):
            raise F7Error("El nombre de etapa no puede estar vacío")
        if any(
            definition.sla_hours is not None and definition.sla_hours <= 0
            for definition in definitions
        ):
            raise F7Error("El SLA de una etapa debe ser mayor que cero")
        existing = list(
            self.session.scalars(
                sa.select(ChangeStage).where(ChangeStage.project_id == project_id)
            ).all()
        )
        if self.session.scalars(
            sa.select(ChangeRequest.id)
            .join(ChangeRequestStage, ChangeRequestStage.request_id == ChangeRequest.id)
            .where(ChangeRequest.project_id == project_id, ChangeRequestStage.status == ChangeStageStatus.ACTIVE)
        ).first():
            raise WorkflowError("No se pueden reordenar etapas con solicitudes activas")
        existing_by_sequence = {stage.sequence: stage for stage in existing}
        configured_sequences = {definition.sequence for definition in definitions}
        for stage in existing:
            stage.is_active = stage.sequence in configured_sequences
        stages: list[ChangeStage] = []
        for definition in definitions:
            stage = existing_by_sequence.get(definition.sequence)
            if stage is None:
                stage = ChangeStage(project_id=project_id, sequence=definition.sequence)
                self.session.add(stage)
            stage.name = definition.name.strip()
            stage.sla_hours = definition.sla_hours
            stage.is_active = True
            stages.append(stage)
        self.session.flush()
        return stages

    def create_change_request(
        self,
        project_id: uuid.UUID,
        *,
        code: str,
        title: str,
        description: str,
        change_type: str,
        priority: str,
        requester_id: uuid.UUID | None = None,
    ) -> ChangeRequest:
        """Create a request and materialize the configured workflow snapshot."""

        self._project(project_id)
        stages = list(
            self.session.scalars(
                sa.select(ChangeStage)
                .where(ChangeStage.project_id == project_id, ChangeStage.is_active.is_(True))
                .order_by(ChangeStage.sequence)
            ).all()
        )
        if not stages:
            stages = self.configure_stages(project_id, DEFAULT_CHANGE_STAGES)
        request = ChangeRequest(
            project_id=project_id,
            code=code.strip(),
            title=title.strip(),
            description=description.strip(),
            change_type=change_type,
            priority=priority,
            requester_id=requester_id,
            current_stage_id=stages[0].id,
        )
        self.session.add(request)
        self.session.flush()
        now = datetime.now(UTC)
        request_stages = [
            ChangeRequestStage(
                request_id=request.id,
                stage_id=stage.id,
                status=ChangeStageStatus.ACTIVE if index == 0 else ChangeStageStatus.PENDING,
                entered_at=now if index == 0 else None,
            )
            for index, stage in enumerate(stages)
        ]
        self.session.add_all(request_stages)
        self._audit(
            "CREATE",
            "ChangeRequest",
            request.id,
            None,
            {"code": request.code},
            requester_id,
        )
        self.session.flush()
        return request

    def create_milestone(self, element_id: uuid.UUID) -> Milestone:
        """Mark a Gantt element as a milestone, idempotently."""

        element = self.session.get(GanttElement, element_id)
        if element is None:
            raise NotFoundError(f"Elemento inexistente: {element_id}")
        if element.element_type != GanttElementType.MILESTONE:
            element.element_type = GanttElementType.MILESTONE
        milestone = self.session.get(Milestone, element_id)
        if milestone is None:
            milestone = Milestone(element_id=element_id)
            self.session.add(milestone)
            self.session.flush()
        return milestone

    def add_criterion(
        self,
        milestone_id: uuid.UUID,
        *,
        external_id: str,
        description: str,
        verification_method: str,
        responsible_id: uuid.UUID | None = None,
    ) -> AcceptanceCriterion:
        """Add an acceptance criterion to a milestone."""

        if self.session.get(Milestone, milestone_id) is None:
            raise NotFoundError(f"Hito inexistente: {milestone_id}")
        criterion = AcceptanceCriterion(
            milestone_id=milestone_id,
            external_id=external_id.strip(),
            description=description.strip(),
            verification_method=verification_method.strip(),
            responsible_id=responsible_id,
        )
        self.session.add(criterion)
        self.session.flush()
        return criterion

    def verify_criterion(
        self,
        criterion_id: uuid.UUID,
        status: CriterionStatus,
        *,
        verified_by: uuid.UUID | None = None,
    ) -> AcceptanceCriterion:
        """Record the status and verifier of an acceptance criterion."""

        criterion = self.session.get(AcceptanceCriterion, criterion_id)
        if criterion is None:
            raise NotFoundError(f"Criterio inexistente: {criterion_id}")
        criterion.status = status
        criterion.verified_by = verified_by
        criterion.verified_at = datetime.now(UTC)
        criteria = self.session.scalars(
            sa.select(AcceptanceCriterion).where(
                AcceptanceCriterion.milestone_id == criterion.milestone_id
            )
        ).all()
        milestone = self.session.get(Milestone, criterion.milestone_id)
        if milestone is not None and criteria:
            if all(item.status == CriterionStatus.MET for item in criteria):
                milestone.acceptance_status = CriterionStatus.MET
            elif any(item.status == CriterionStatus.NOT_MET for item in criteria):
                milestone.acceptance_status = CriterionStatus.NOT_MET
            else:
                milestone.acceptance_status = CriterionStatus.PENDING
        self.session.flush()
        return criterion

    def transition(
        self,
        request_id: uuid.UUID,
        to_status: ChangeStatus,
        *,
        user_id: uuid.UUID | None = None,
        comment: str | None = None,
    ) -> ChangeRequest:
        """Advance a request, enforcing order and recording an append-only log."""

        request = self._request(request_id)
        active = self.session.scalar(
            sa.select(ChangeRequestStage).where(
                ChangeRequestStage.request_id == request_id,
                ChangeRequestStage.status == ChangeStageStatus.ACTIVE,
            )
        )
        if active is None:
            raise WorkflowError("La solicitud no tiene una etapa activa")
        if to_status in {ChangeStatus.REJECTED, ChangeStatus.CANCELLED}:
            return self._finish_request(request, active, to_status, user_id, comment)
        if to_status not in {ChangeStatus.APPROVED, ChangeStatus.CLOSED}:
            raise WorkflowError(f"Transición no soportada: {to_status}")
        current_stage = self.session.get(ChangeStage, active.stage_id)
        if current_stage is None:
            raise NotFoundError("Etapa de solicitud inexistente")
        next_stage = self.session.scalar(
            sa.select(ChangeStage).where(
                ChangeStage.project_id == request.project_id,
                ChangeStage.sequence == current_stage.sequence + 1,
                ChangeStage.is_active.is_(True),
            )
        )
        if next_stage is not None and to_status == ChangeStatus.APPROVED:
            active.status = ChangeStageStatus.COMPLETED
            active.exited_at = datetime.now(UTC)
            active.notes = comment
            next_record = self.session.scalar(
                sa.select(ChangeRequestStage).where(
                    ChangeRequestStage.request_id == request.id,
                    ChangeRequestStage.stage_id == next_stage.id,
                )
            )
            if next_record is None:
                raise WorkflowError("La instantánea de etapas está incompleta")
            next_record.status = ChangeStageStatus.ACTIVE
            next_record.entered_at = datetime.now(UTC)
            request.current_stage_id = next_stage.id
            self._transition(request, active, next_record, to_status, user_id, comment)
            return request
        if next_stage is not None:
            raise WorkflowError("La aprobación solo es válida en la última etapa")
        return self._finish_request(request, active, to_status, user_id, comment)

    def workflow_status(self, request_id: uuid.UUID) -> dict[str, object]:
        """Return active stage SLA timing for dashboards and escalation jobs."""

        request = self._request(request_id)
        active = self.session.scalar(
            sa.select(ChangeRequestStage).where(
                ChangeRequestStage.request_id == request.id,
                ChangeRequestStage.status == ChangeStageStatus.ACTIVE,
            )
        )
        if active is None:
            return {"request_id": request.id, "active": False, "sla_breached": False}
        stage = self.session.get(ChangeStage, active.stage_id)
        entered_at = active.entered_at or datetime.now(UTC)
        due_at = (
            entered_at + timedelta(hours=stage.sla_hours)
            if stage is not None and stage.sla_hours is not None
            else None
        )
        return {
            "request_id": request.id,
            "active": True,
            "stage_id": active.stage_id,
            "stage_name": stage.name if stage else None,
            "entered_at": entered_at,
            "sla_hours": stage.sla_hours if stage else None,
            "due_at": due_at,
            "sla_breached": due_at is not None and datetime.now(UTC) > due_at,
        }

    def compare_baseline(
        self, project_id: uuid.UUID, baseline_id: uuid.UUID, updates: Iterable[TaskUpdate]
    ) -> BaselineComparison:
        """Compare proposal fields with the immutable baseline snapshot."""

        baseline = self.session.scalar(
            sa.select(Baseline).where(Baseline.id == baseline_id, Baseline.project_id == project_id)
        )
        if baseline is None:
            raise NotFoundError("Línea base inexistente")
        proposal_updates = tuple(updates)
        proposed = {update.task_id: update.values() for update in proposal_updates}
        snapshots = self.session.scalars(
            sa.select(BaselineElement).where(BaselineElement.baseline_id == baseline.id)
        ).all()
        snapshot_ids = {snapshot.external_id for snapshot in snapshots}
        unknown_ids = set(proposed) - snapshot_ids
        if unknown_ids:
            raise F7Error(f"Elemento inexistente en línea base: {sorted(unknown_ids)[0]}")
        changes: list[dict[str, object]] = []
        for snapshot in snapshots:
            values = proposed.get(snapshot.external_id, {})
            fields = {
                "planned_start": snapshot.planned_start,
                "planned_finish": snapshot.planned_finish,
                "duration_days": snapshot.duration_days,
                "planned_cost": snapshot.planned_cost,
            }
            translated = {
                "planned_start": values.get("start", fields["planned_start"]),
                "planned_finish": values.get("finish", fields["planned_finish"]),
                "duration_days": values.get("duration_days", fields["duration_days"]),
                "planned_cost": values.get("planned_cost", fields["planned_cost"]),
            }
            difference = {
                field_name: {"before": before, "after": translated[field_name]}
                for field_name, before in fields.items()
                if before != translated[field_name]
            }
            if difference:
                changes.append({"external_id": snapshot.external_id, "changes": difference})
        return BaselineComparison(baseline.version, tuple(changes))

    def simulate_change(
        self,
        request_id: uuid.UUID,
        updates: Iterable[TaskUpdate],
    ) -> ImpactResult:
        """Persist a new what-if impact while leaving the current plan intact."""

        request = self._request(request_id)
        project = self._project(request.project_id)
        self._use_project_engine(project)
        baseline = self.session.scalar(
            sa.select(Baseline).where(
                Baseline.project_id == project.id, Baseline.status == BaselineStatus.ACTIVE
            )
        )
        tasks, resources, assignments = self._planning_graph(project)
        proposal_updates = tuple(updates)
        result = self.impact_analyzer.simulate(
            tasks,
            resources,
            assignments,
            proposal_updates,
            project_start=project.planned_start,
            project_deadline=project.committed_finish,
            contingency_pct=project.contingency_pct,
        )
        self.session.add(
            ChangeImpact(
                request_id=request.id,
                baseline_id=baseline.id if baseline else None,
                proposed_project_finish=result.proposed_finish,
                delta_schedule_days=result.delta_schedule_days,
                delta_cost=result.delta_cost,
                delta_contingency=result.delta_contingency,
                affected_elements=_json_safe(list(result.affected_elements)),
                resource_effect=_json_safe(result.resource_effect),
                summary=(
                    f"Plazo {result.delta_schedule_days} días; "
                    f"costo {result.delta_cost}; reserva {result.delta_contingency}"
                ),
            )
        )
        self.session.flush()
        return result

    def apply_change(
        self,
        request_id: uuid.UUID,
        updates: Iterable[TaskUpdate],
        *,
        user_id: uuid.UUID | None = None,
    ) -> Baseline:
        """Apply an approved proposal and create the next immutable baseline."""

        request = self._request(request_id)
        if request.status != ChangeStatus.APPROVED:
            raise WorkflowError("Solo se puede aplicar una solicitud aprobada")
        project = self._project(request.project_id)
        self._use_project_engine(project)
        proposal_updates = tuple(updates)
        baseline = self.session.scalar(
            sa.select(Baseline).where(
                Baseline.project_id == project.id, Baseline.status == BaselineStatus.ACTIVE
            )
        )
        tasks, resources, assignments = self._planning_graph(project)
        result = self.impact_analyzer.simulate(
            tasks,
            resources,
            assignments,
            proposal_updates,
            project_start=project.planned_start,
            project_deadline=project.committed_finish,
            contingency_pct=project.contingency_pct,
        )
        self.session.add(
            ChangeImpact(
                request_id=request.id,
                baseline_id=baseline.id if baseline else None,
                proposed_project_finish=result.proposed_finish,
                delta_schedule_days=result.delta_schedule_days,
                delta_cost=result.delta_cost,
                delta_contingency=result.delta_contingency,
                affected_elements=_json_safe(list(result.affected_elements)),
                resource_effect=_json_safe(result.resource_effect),
                summary=(
                    f"Plazo {result.delta_schedule_days} días; "
                    f"costo {result.delta_cost}; reserva {result.delta_contingency}"
                ),
            )
        )
        self._persist_proposal(project, tasks, resources, assignments, proposal_updates)
        recalculate_project(self.session, project)
        new_baseline = self._snapshot_baseline(project, baseline, user_id)
        request.status = ChangeStatus.CLOSED
        request.closed_at = datetime.now(UTC)
        self._audit(
            "APPLY",
            "ChangeRequest",
            request.id,
            {"status": ChangeStatus.APPROVED.value},
            {"status": ChangeStatus.CLOSED.value, "baseline": new_baseline.version},
            user_id,
        )
        self.session.flush()
        return new_baseline

    def add_evidence(
        self,
        *,
        file_name: str,
        storage_key: str,
        content_type: str | None = None,
        size_bytes: int | None = None,
        change_request_id: uuid.UUID | None = None,
        criterion_id: uuid.UUID | None = None,
        uploaded_by: uuid.UUID | None = None,
    ) -> Evidence:
        """Attach evidence to exactly one criterion or change request."""

        if (change_request_id is None) == (criterion_id is None):
            raise F7Error("La evidencia debe pertenecer a un criterio o una solicitud")
        if not file_name.strip() or not storage_key.strip():
            raise F7Error("El archivo y la clave de almacenamiento son obligatorios")
        if size_bytes is not None and size_bytes < 0:
            raise F7Error("El tamaño de evidencia no puede ser negativo")
        evidence = Evidence(
            file_name=file_name.strip(),
            storage_key=storage_key.strip(),
            content_type=content_type,
            size_bytes=size_bytes,
            change_request_id=change_request_id,
            criterion_id=criterion_id,
            uploaded_by=uploaded_by,
        )
        self.session.add(evidence)
        self.session.flush()
        self._audit("UPLOAD", "Evidence", evidence.id, None, {"file_name": evidence.file_name}, uploaded_by)
        return evidence

    def _planning_graph(
        self, project: Project
    ) -> tuple[list[Task], list[DomainResource], list[DomainAssignment]]:
        elements = list(
            self.session.scalars(
                sa.select(GanttElement).where(GanttElement.project_id == project.id)
            ).all()
        )
        by_id = {element.id: element for element in elements}
        dependency_rows = list(
            self.session.scalars(
                sa.select(Dependency)
                .join(GanttElement, Dependency.predecessor_id == GanttElement.id)
                .where(GanttElement.project_id == project.id)
            ).all()
        )
        resources = list(
            self.session.scalars(sa.select(Resource).where(Resource.project_id == project.id)).all()
        )
        resource_map = {resource.id: resource for resource in resources}
        assignments_rows = list(
            self.session.scalars(
                sa.select(AssignmentRow)
                .join(GanttElement, AssignmentRow.element_id == GanttElement.id)
                .where(GanttElement.project_id == project.id)
            ).all()
        )
        dependencies: dict[uuid.UUID, list[DomainDependency]] = {element.id: [] for element in elements}
        for dependency in dependency_rows:
            dependencies[dependency.successor_id].append(
                DomainDependency(
                    by_id[dependency.predecessor_id].external_id,
                    dependency.dependency_type.value,
                    dependency.lag_days,
                )
            )
        domain_resources = [
            DomainResource(
                str(resource.id),
                resource.name,
                DomainResourceType(resource.resource_type.value),
                resource.rate,
                resource.rate,
                resource.capacity_hours_per_day or Decimal("8"),
            )
            for resource in resources
        ]
        domain_assignments = [
            DomainAssignment(
                by_id[row.element_id].external_id,
                str(row.resource_id),
                row.planned_hours,
                row.quantity,
                row.hours_per_day,
                row.rate_override,
            )
            for row in assignments_rows
            if row.resource_id in resource_map
        ]
        domain_tasks = [
            Task(
                element.external_id,
                element.name,
                element.element_type.value,
                by_id[element.parent_id].external_id if element.parent_id in by_id else None,
                element.planned_start,
                element.planned_finish,
                element.duration_days,
                tuple(dependencies[element.id]),
                element.effort_hours,
                element.progress_pct,
                element.actual_start,
                element.actual_finish,
                element.actual_cost,
                element.planned_cost,
                element.total_slack_days,
                element.free_slack_days,
                element.is_critical,
                tuple(
                    assignment
                    for assignment in domain_assignments
                    if assignment.task_id == element.external_id
                ),
            )
            for element in elements
        ]
        return domain_tasks, domain_resources, domain_assignments

    def _use_project_engine(self, project: Project) -> None:
        """Use the project's calendar while retaining the shared engine."""

        self.engine = DeterministicCalculationEngine(project_calendar(self.session, project))
        self.impact_analyzer = ImpactAnalyzer(self.engine)

    def _persist_proposal(
        self,
        project: Project,
        tasks: Iterable[Task],
        resources: Iterable[DomainResource],
        assignments: Iterable[DomainAssignment],
        updates: Iterable[TaskUpdate],
    ) -> None:
        """Schedule the proposal and update current plan rows, never snapshots."""

        task_list = list(copy.deepcopy(tuple(tasks)))
        self._apply_updates_to_tasks(task_list, updates)
        scheduled = self.engine.schedule(
            task_list, project_start=project.planned_start, project_deadline=project.committed_finish
        )
        cost_report = self.engine.calculate_costs(scheduled.tasks.values(), resources, assignments)
        cost_overrides = {
            update.task_id: update.planned_cost
            for update in updates
            if update.planned_cost is not None
        }
        rows = {
            row.external_id: row
            for row in self.session.scalars(
                sa.select(GanttElement).where(GanttElement.project_id == project.id)
            ).all()
        }
        for task_id, task in scheduled.tasks.items():
            row = rows[task_id]
            row.planned_start = task.start
            row.planned_finish = task.finish
            row.duration_days = task.duration_days
            row.planned_cost = cost_overrides.get(
                task_id, cost_report.consolidated[task_id].planned_cost
            )
            row.total_slack_days = task.total_slack_days
            row.free_slack_days = task.free_slack_days
            row.is_critical = task.critical

    @staticmethod
    def _apply_updates_to_tasks(tasks: list[Task], updates: Iterable[TaskUpdate]) -> None:
        task_map = {task.task_id: task for task in tasks}
        for update in updates:
            task = task_map.get(update.task_id)
            if task is None:
                raise F7Error(f"Elemento inexistente en propuesta: {update.task_id}")
            for field_name, value in update.values().items():
                setattr(task, field_name, value)

    def _snapshot_baseline(
        self, project: Project, previous: Baseline | None, user_id: uuid.UUID | None
    ) -> Baseline:
        if previous is not None:
            previous.status = BaselineStatus.SUPERSEDED
            self.session.flush()
            previous_version = _baseline_number(previous.version)
        else:
            previous_version = 0
        baseline = Baseline(
            project_id=project.id,
            version=f"v{previous_version + 1}",
            status=BaselineStatus.ACTIVE,
            created_by=user_id,
        )
        self.session.add(baseline)
        self.session.flush()
        rows = self.session.scalars(
            sa.select(GanttElement).where(GanttElement.project_id == project.id)
        ).all()
        self.session.add_all(
            [
                BaselineElement(
                    baseline_id=baseline.id,
                    project_id=project.id,
                    element_id=row.id,
                    external_id=row.external_id,
                    parent_external_id=(
                        self.session.get(GanttElement, row.parent_id).external_id
                        if row.parent_id is not None and self.session.get(GanttElement, row.parent_id)
                        else None
                    ),
                    element_type=row.element_type,
                    name=row.name,
                    planned_start=row.planned_start,
                    planned_finish=row.planned_finish,
                    duration_days=row.duration_days,
                    planned_cost=row.planned_cost,
                )
                for row in rows
            ]
        )
        baseline.approved_at = datetime.now(UTC)
        self._audit("CREATE", "Baseline", baseline.id, None, {"version": baseline.version}, user_id)
        return baseline

    def _finish_request(
        self,
        request: ChangeRequest,
        active: ChangeRequestStage,
        status: ChangeStatus,
        user_id: uuid.UUID | None,
        comment: str | None,
    ) -> ChangeRequest:
        active.status = ChangeStageStatus.COMPLETED if status != ChangeStatus.CANCELLED else ChangeStageStatus.SKIPPED
        active.exited_at = datetime.now(UTC)
        active.completed_by = user_id
        active.notes = comment
        request.status = status
        request.decided_at = datetime.now(UTC)
        self._transition(request, active, None, status, user_id, comment)
        return request

    def _transition(
        self,
        request: ChangeRequest,
        active: ChangeRequestStage,
        next_stage: ChangeRequestStage | None,
        status: ChangeStatus,
        user_id: uuid.UUID | None,
        comment: str | None,
    ) -> None:
        self.session.add(
            ChangeTransition(
                request_id=request.id,
                from_stage_id=active.stage_id,
                to_stage_id=next_stage.stage_id if next_stage else None,
                from_status=request.status,
                to_status=status,
                performed_by=user_id,
                comment=comment,
            )
        )

    def _audit(
        self,
        action: str,
        entity_type: str,
        entity_id: uuid.UUID | None,
        before: dict[str, object] | None,
        after: dict[str, object] | None,
        user_id: uuid.UUID | None = None,
    ) -> None:
        self.session.add(
            AuditLog(
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                before_data=before,
                after_data=after,
                user_id=user_id,
            )
        )

    def _project(self, project_id: uuid.UUID) -> Project:
        project = self.session.get(Project, project_id)
        if project is None:
            raise NotFoundError(f"Proyecto inexistente: {project_id}")
        return project

    def _request(self, request_id: uuid.UUID) -> ChangeRequest:
        request = self.session.get(ChangeRequest, request_id)
        if request is None:
            raise NotFoundError(f"Solicitud inexistente: {request_id}")
        return request


def _baseline_number(version: str) -> int:
    """Extract the numeric part of a version such as ``v3``."""

    match = re.fullmatch(r"v(\d+)", version.strip(), re.IGNORECASE)
    if match is None:
        raise F7Error(f"Versión de línea base inválida: {version}")
    return int(match.group(1))


def _json_safe(value: object) -> object:
    """Convert Decimal/date values before writing JSONB or an API payload."""

    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    return value
