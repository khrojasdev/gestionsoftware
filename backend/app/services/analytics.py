"""Read-side analytics: forecast, status, EVM, KPI variables and resource load.

Everything here is deterministic and calculated from the persisted plan, the
active baseline, recorded progress and the project calendar.  The module never
writes to the database, so the HTTP views can call it freely.
"""

from __future__ import annotations

import math
import uuid
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.domain.models import Dependency as DomainDependency
from app.domain.models import Task
from app.models import (
    Assignment,
    Baseline,
    BaselineElement,
    BaselineStatus,
    ChangeImpact,
    ChangeRequest,
    ChangeRequestStage,
    ChangeStage,
    ChangeStageStatus,
    ChangeStatus,
    Dependency,
    Evidence,
    GanttElement,
    ManualMetric,
    Project,
    Resource,
    ResourceType,
)
from app.services.calendar import BusinessCalendar
from app.services.scheduler import Scheduler

ZERO = Decimal("0")
HUNDRED = Decimal("100")
LEAF_TYPES = {"SUBACTIVIDAD", "HITO"}

STATUS_LABELS = {
    "COMPLETADA": "Completada",
    "COMPLETADA_ATRASO": "Completada con atraso",
    "EN_CURSO": "En curso",
    "ATRASADA": "Atrasada",
    "EN_RIESGO": "Desplazada",
    "NO_INICIADA": "No iniciada",
}

MANUAL_METRICS: dict[str, str] = {
    "CHANGE_ADOPTION_INDEX": "Índice de adopción (% usuarios activos sobre capacitados)",
    "CHANGE_TRAINING_COVERAGE": "Cobertura de capacitación (% usuarios capacitados sobre objetivo)",
}


def _d(value: Any) -> Decimal:
    if value is None:
        return ZERO
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass
class ElementState:
    """Calculated view of one Gantt element at the project cut-off."""

    id: uuid.UUID
    external_id: str
    kind: str
    name: str
    parent_external_id: str | None
    start: date | None
    finish: date | None
    duration_days: int | None
    progress_pct: Decimal
    actual_start: date | None
    actual_finish: date | None
    planned_cost: Decimal
    actual_cost: Decimal
    is_critical: bool
    total_slack_days: int | None
    free_slack_days: int | None
    baseline_start: date | None = None
    baseline_finish: date | None = None
    baseline_cost: Decimal | None = None
    forecast_start: date | None = None
    forecast_finish: date | None = None
    planned_pct: Decimal = ZERO
    status: str = "NO_INICIADA"
    slip_days: int = 0
    children: list[str] = field(default_factory=list)
    predecessors: list[dict[str, Any]] = field(default_factory=list)
    resources: list[str] = field(default_factory=list)

    @property
    def is_leaf(self) -> bool:
        return self.kind in LEAF_TYPES


class ProjectAnalytics:
    """Load a project once and expose every derived read model."""

    def __init__(self, session: Session, project: Project, cutoff: date | None = None) -> None:
        self.session = session
        self.project = project
        self.cutoff = cutoff or project.cutoff_date or date.today()
        self.calendar = _calendar(session, project)
        self._load()
        self._compute_states()

    # ------------------------------------------------------------------ load
    def _load(self) -> None:
        session, project_id = self.session, self.project.id
        self.elements = list(
            session.scalars(sa.select(GanttElement).where(GanttElement.project_id == project_id)).all()
        )
        self.by_id = {element.id: element for element in self.elements}
        self.dependencies = list(
            session.scalars(sa.select(Dependency).where(Dependency.project_id == project_id)).all()
        )
        self.resources = list(
            session.scalars(
                sa.select(Resource).where(Resource.project_id == project_id).order_by(Resource.external_id)
            ).all()
        )
        self.resource_by_id = {resource.id: resource for resource in self.resources}
        self.assignments = list(
            session.scalars(sa.select(Assignment).where(Assignment.project_id == project_id)).all()
        )
        self.baseline = session.scalar(
            sa.select(Baseline).where(Baseline.project_id == project_id, Baseline.status == BaselineStatus.ACTIVE)
        )
        self.first_baseline = session.scalar(
            sa.select(Baseline).where(Baseline.project_id == project_id).order_by(Baseline.created_at).limit(1)
        )
        self.baseline_rows: dict[str, BaselineElement] = {}
        if self.baseline is not None:
            for row in session.scalars(
                sa.select(BaselineElement).where(BaselineElement.baseline_id == self.baseline.id)
            ).all():
                self.baseline_rows[row.external_id] = row

    # --------------------------------------------------------------- states
    def _compute_states(self) -> None:
        states: dict[str, ElementState] = {}
        for element in self.elements:
            parent = self.by_id.get(element.parent_id) if element.parent_id else None
            base = self.baseline_rows.get(element.external_id)
            states[element.external_id] = ElementState(
                id=element.id,
                external_id=element.external_id,
                kind=element.element_type.value,
                name=element.name,
                parent_external_id=parent.external_id if parent else None,
                start=element.planned_start,
                finish=element.planned_finish,
                duration_days=element.duration_days,
                progress_pct=_d(element.progress_pct),
                actual_start=element.actual_start,
                actual_finish=element.actual_finish,
                planned_cost=_d(element.planned_cost),
                actual_cost=_d(element.actual_cost),
                is_critical=bool(element.is_critical),
                total_slack_days=element.total_slack_days,
                free_slack_days=element.free_slack_days,
                baseline_start=base.planned_start if base else None,
                baseline_finish=base.planned_finish if base else None,
                baseline_cost=_d(base.planned_cost) if base else None,
            )
        for state in states.values():
            if state.parent_external_id in states:
                states[state.parent_external_id].children.append(state.external_id)
        for dependency in self.dependencies:
            predecessor = self.by_id.get(dependency.predecessor_id)
            successor = self.by_id.get(dependency.successor_id)
            if predecessor is None or successor is None:
                continue
            states[successor.external_id].predecessors.append(
                {
                    "id": str(dependency.id),
                    "predecessor": predecessor.external_id,
                    "type": dependency.dependency_type.value,
                    "lag_days": dependency.lag_days,
                }
            )
        for assignment in self.assignments:
            element = self.by_id.get(assignment.element_id)
            resource = self.resource_by_id.get(assignment.resource_id)
            if element is not None and resource is not None:
                states[element.external_id].resources.append(resource.name)
        self.states = states
        self._forecast()
        for state in states.values():
            if state.is_leaf:
                self._classify(state)
        self._consolidate()

    def leaves(self) -> list[ElementState]:
        return [state for state in self.states.values() if state.is_leaf]

    def subactivities(self) -> list[ElementState]:
        return [state for state in self.states.values() if state.kind == "SUBACTIVIDAD"]

    def milestones(self) -> list[ElementState]:
        return sorted(
            (state for state in self.states.values() if state.kind == "HITO"),
            key=lambda item: (item.baseline_finish or item.finish or date.max, item.external_id),
        )

    def _forecast(self) -> None:
        """Project dates from recorded progress and propagate to successors."""

        cutoff = self.cutoff
        tasks: list[Task] = []
        for state in self.leaves():
            if state.start is None:
                continue
            duration = state.duration_days or 0
            start = state.start
            predecessors = tuple(
                DomainDependency(item["predecessor"], item["type"], item["lag_days"])
                for item in state.predecessors
                if item["predecessor"] in self.states and self.states[item["predecessor"]].is_leaf
            )
            progress = state.progress_pct
            if progress >= HUNDRED:
                start = state.actual_start or state.start
                finish = state.actual_finish or state.finish or start
                duration = 0 if state.kind == "HITO" else max(1, self.calendar.working_days_inclusive(start, finish))
                predecessors = ()
            elif progress > ZERO:
                start = state.actual_start or state.start
                remaining = math.ceil(Decimal(duration) * (HUNDRED - progress) / HUNDRED)
                elapsed = self.calendar.working_days_inclusive(start, cutoff) if cutoff >= start else 0
                duration = max(1, elapsed + remaining)
                predecessors = ()
            elif start <= cutoff and state.kind != "HITO":
                start = self.calendar.next_working_day(cutoff + timedelta(days=1))
            tasks.append(
                Task(
                    state.external_id,
                    kind=state.kind,
                    start=start,
                    duration_days=duration,
                    predecessors=predecessors,
                )
            )
        if not tasks:
            return
        try:
            result = Scheduler(self.calendar).schedule(tasks)
        except ValueError:
            for state in self.leaves():
                state.forecast_start, state.forecast_finish = state.start, state.finish
            return
        for task_id, task in result.tasks.items():
            state = self.states[task_id]
            state.forecast_start = task.start
            state.forecast_finish = task.finish
            if state.progress_pct >= HUNDRED and state.actual_finish:
                state.forecast_finish = state.actual_finish

    def _classify(self, state: ElementState) -> None:
        start = state.baseline_start or state.start
        finish = state.baseline_finish or state.finish
        duration = state.duration_days or 0
        state.planned_pct = self.planned_pct(start, finish, duration, self.cutoff)
        reference = finish or state.finish
        if state.forecast_finish and reference:
            state.slip_days = max(0, self.calendar.working_days_between(reference, state.forecast_finish))
        progress = state.progress_pct
        if progress >= HUNDRED:
            late = bool(state.actual_finish and reference and state.actual_finish > reference)
            state.status = "COMPLETADA_ATRASO" if late else "COMPLETADA"
        elif progress > ZERO:
            state.status = "ATRASADA" if state.planned_pct * HUNDRED - progress > Decimal("8") else "EN_CURSO"
        elif start is not None and start <= self.cutoff and (state.kind != "HITO" or (finish and finish < self.cutoff)):
            state.status = "ATRASADA"
        elif state.slip_days > 0:
            state.status = "EN_RIESGO"
        else:
            state.status = "NO_INICIADA"

    def planned_pct(self, start: date | None, finish: date | None, duration: int, cutoff: date) -> Decimal:
        if start is None:
            return ZERO
        finish = finish or self.calendar.duration_finish(start, duration)
        if duration == 0:
            return Decimal("1") if cutoff >= finish else ZERO
        if cutoff < start:
            return ZERO
        if cutoff >= finish:
            return Decimal("1")
        elapsed = self.calendar.working_days_inclusive(start, cutoff)
        return min(Decimal("1"), Decimal(elapsed) / Decimal(max(duration, 1)))

    def _consolidate(self) -> None:
        def visit(external_id: str) -> None:
            state = self.states[external_id]
            if state.is_leaf or not state.children:
                return
            for child in state.children:
                visit(child)
            children = [self.states[child] for child in state.children]
            weight = sum((child.planned_cost for child in children), ZERO)
            state.forecast_start = _min(child.forecast_start for child in children)
            state.forecast_finish = _max(child.forecast_finish for child in children)
            state.baseline_start = _min(child.baseline_start for child in children)
            state.baseline_finish = _max(child.baseline_finish for child in children)
            state.baseline_cost = sum((child.baseline_cost or ZERO for child in children), ZERO)
            state.planned_pct = (
                sum((child.planned_pct * child.planned_cost for child in children), ZERO) / weight
                if weight
                else ZERO
            )
            state.is_critical = any(child.is_critical for child in children)
            if state.baseline_finish and state.forecast_finish:
                state.slip_days = max(
                    0, self.calendar.working_days_between(state.baseline_finish, state.forecast_finish)
                )
            statuses = {child.status for child in children}
            if statuses <= {"COMPLETADA", "COMPLETADA_ATRASO"}:
                state.status = "COMPLETADA_ATRASO" if "COMPLETADA_ATRASO" in statuses else "COMPLETADA"
            elif "ATRASADA" in statuses:
                state.status = "ATRASADA"
            elif statuses & {"EN_CURSO", "COMPLETADA", "COMPLETADA_ATRASO"}:
                state.status = "EN_CURSO"
            elif "EN_RIESGO" in statuses:
                state.status = "EN_RIESGO"
            else:
                state.status = "NO_INICIADA"

        for state in self.states.values():
            if state.parent_external_id is None:
                visit(state.external_id)

    # ------------------------------------------------------------------ EVM
    def progress_as_of(self, state: ElementState, at: date) -> Decimal:
        """Estimate the progress a leaf had on ``at`` from its actual dates."""

        if at >= self.cutoff:
            return state.progress_pct
        if state.actual_finish and state.actual_finish <= at:
            return HUNDRED
        if state.actual_start is None or state.actual_start > at:
            return ZERO
        span_end = state.actual_finish or self.cutoff
        total = max(1, self.calendar.working_days_inclusive(state.actual_start, span_end))
        elapsed = self.calendar.working_days_inclusive(state.actual_start, at)
        final = HUNDRED if state.actual_finish else state.progress_pct
        return min(final, final * Decimal(elapsed) / Decimal(total))

    def evm(self, at: date | None = None) -> dict[str, Decimal]:
        at = at or self.cutoff
        bac = pv = ev = ac = ZERO
        for state in self.subactivities():
            cost = state.planned_cost
            start = state.baseline_start or state.start
            finish = state.baseline_finish or state.finish
            planned = self.planned_pct(start, finish, state.duration_days or 0, at)
            progress = self.progress_as_of(state, at)
            bac += cost
            pv += cost * planned
            ev += cost * progress / HUNDRED
            if state.progress_pct > ZERO:
                ac += state.actual_cost * (progress / state.progress_pct)
        spi = ev / pv if pv else ZERO
        cpi = ev / ac if ac else ZERO
        eac = bac / cpi if cpi else bac
        return {
            "BAC": bac,
            "PV": pv,
            "EV": ev,
            "AC": ac,
            "SPI": spi,
            "CPI": cpi,
            "SV": ev - pv,
            "CV": ev - ac,
            "EAC": eac,
            "ETC": eac - ac,
            "VAC": bac - eac,
        }

    def contingency_amount(self) -> Decimal:
        base = ZERO
        if self.first_baseline is not None:
            base = sum(
                (
                    _d(row.planned_cost)
                    for row in self.session.scalars(
                        sa.select(BaselineElement).where(
                            BaselineElement.baseline_id == self.first_baseline.id,
                            BaselineElement.element_type == "SUBACTIVIDAD",
                        )
                    ).all()
                ),
                ZERO,
            )
        budget = _d(self.project.budget)
        if budget > base > ZERO:
            return budget - base
        return (base or budget) * _d(self.project.contingency_pct) / HUNDRED

    def project_finish(self) -> dict[str, date | None]:
        leaves = self.leaves()
        return {
            "baseline": _max(state.baseline_finish for state in leaves),
            "plan": _max(state.finish for state in leaves),
            "forecast": _max(state.forecast_finish for state in leaves),
            "start": _min(state.start for state in leaves),
        }

    # ------------------------------------------------------------ variables
    def metrics(self, at: date | None = None) -> dict[str, Any]:
        """Return every KPI catalogue variable for the cut-off ``at``."""

        at = at or self.cutoff
        values: dict[str, Any] = dict(self.evm(at))
        subactivities = self.subactivities()
        weight = sum((state.planned_cost for state in subactivities), ZERO)
        real = plan = ZERO
        started: list[ElementState] = []
        late: list[ElementState] = []
        for state in subactivities:
            start = state.baseline_start or state.start
            finish = state.baseline_finish or state.finish
            planned = self.planned_pct(start, finish, state.duration_days or 0, at)
            progress = self.progress_as_of(state, at)
            real += state.planned_cost * progress / HUNDRED
            plan += state.planned_cost * planned
            if start is not None and start <= at:
                started.append(state)
                if progress < HUNDRED and planned * HUNDRED - progress > Decimal("8"):
                    late.append(state)
        values["AVANCE_REAL"] = real / weight * HUNDRED if weight else ZERO
        values["AVANCE_PLAN"] = plan / weight * HUNDRED if weight else ZERO
        values["PHYSICAL_PROGRESS_DEVIATION"] = values["AVANCE_REAL"] - values["AVANCE_PLAN"]
        values["ADVANCE_GAP"] = values["PHYSICAL_PROGRESS_DEVIATION"]
        values["ACTIVIDADES"] = [1] * len(started)
        values["ACTIVIDADES_ATRASADAS"] = [1] * len(late)
        values["LATE_ACTIVITIES_PCT"] = _ratio(len(late), len(started)) * HUNDRED
        values["LATE_TASKS"] = _ratio(len(late), len(started))

        milestones = self.milestones()
        done = [m for m in milestones if self.progress_as_of(m, at) >= HUNDRED]
        on_time = [m for m in done if not (m.actual_finish and (m.baseline_finish or m.finish) and m.actual_finish > (m.baseline_finish or m.finish))]
        values["HITOS"] = [1] * len(milestones)
        values["HITOS_A_TIEMPO"] = [1] * len(on_time)
        values["MILESTONES_ON_TIME_PCT"] = _ratio(len(on_time), len(done)) * HUNDRED if done else HUNDRED
        values["MILESTONE_ON_TIME"] = _ratio(len(on_time), len(milestones))
        closing = milestones[-1] if milestones else None
        deviation = 0
        if closing is not None and closing.forecast_finish and (closing.baseline_finish or closing.finish):
            deviation = self.calendar.working_days_between(closing.baseline_finish or closing.finish, closing.forecast_finish)
        values["CLOSING_MILESTONE_DEVIATION"] = Decimal(deviation)
        values["CLOSE_VARIANCE"] = Decimal(deviation)
        if closing is not None:
            values["FECHA_CIERRE_BASE"] = Decimal((closing.baseline_finish or closing.finish or at).toordinal())
            values["FECHA_CIERRE_REAL"] = Decimal((closing.forecast_finish or closing.finish or at).toordinal())
        else:
            values["FECHA_CIERRE_BASE"] = values["FECHA_CIERRE_REAL"] = Decimal(at.toordinal())
        values.update(self.change_metrics(at))
        manual = {
            row.code.upper(): _d(row.value)
            for row in self.session.scalars(
                sa.select(ManualMetric).where(ManualMetric.project_id == self.project.id)
            ).all()
        }
        for code in MANUAL_METRICS:
            values[code] = manual.get(code, ZERO)
        values.update({code: value for code, value in manual.items() if code not in values})
        legacy = (
            "CHANGE_REQUESTS", "CHANGE_APPROVAL_RATE", "CHANGE_REJECTION_RATE", "CHANGE_AVG_CYCLE_HOURS",
            "CHANGE_AVG_IMPACT_HOURS", "CHANGE_IMPACT_COST", "CHANGE_IMPACT_DAYS", "CHANGE_EVIDENCE_COMPLETE_PCT",
            "CHANGE_SLA_BREACHES", "CHANGE_CONTINGENCY_CONSUMPTION", "CHANGE_ADOPTION_INDEX", "CHANGE_TRAINING_COVERAGE",
        )
        for index, code in enumerate(legacy, start=1):
            values[f"VALOR_{index:02d}"] = values[code]
        return values

    def change_metrics(self, at: date | None = None) -> dict[str, Decimal]:
        at_dt = datetime.combine(at or self.cutoff, time.max, tzinfo=UTC)
        project_id = self.project.id
        requests = [
            request
            for request in self.session.scalars(
                sa.select(ChangeRequest).where(ChangeRequest.project_id == project_id)
            ).all()
            if request.created_at <= at_dt
        ]
        decided = [r for r in requests if r.decided_at and r.decided_at <= at_dt or r.status in {ChangeStatus.REJECTED}]
        approved = [r for r in decided if r.status in {ChangeStatus.APPROVED, ChangeStatus.CLOSED}]
        rejected = [r for r in decided if r.status == ChangeStatus.REJECTED]
        finished = [r for r in requests if r.closed_at and r.closed_at <= at_dt] + [
            r for r in rejected if r.closed_at is None and r.decided_at
        ]
        cycle = [
            Decimal(str(((r.closed_at or r.decided_at) - r.created_at).total_seconds() / 3600))
            for r in finished
            if (r.closed_at or r.decided_at)
        ]
        impacts_by_request: dict[uuid.UUID, list[ChangeImpact]] = defaultdict(list)
        if requests:
            for impact in self.session.scalars(
                sa.select(ChangeImpact)
                .where(ChangeImpact.request_id.in_([r.id for r in requests]))
                .order_by(ChangeImpact.simulated_at)
            ).all():
                if impact.simulated_at <= at_dt:
                    impacts_by_request[impact.request_id].append(impact)
        impact_hours = [
            Decimal(str((impacts_by_request[r.id][0].simulated_at - r.created_at).total_seconds() / 3600))
            for r in requests
            if impacts_by_request.get(r.id)
        ]
        approved_impacts = [impacts_by_request[r.id][-1] for r in approved if impacts_by_request.get(r.id)]
        impact_cost = sum((_d(impact.delta_cost) for impact in approved_impacts), ZERO)
        impact_days = sum((impact.delta_schedule_days for impact in approved_impacts), 0)
        with_evidence = set()
        if requests:
            with_evidence = set(
                self.session.scalars(
                    sa.select(Evidence.change_request_id).where(
                        Evidence.change_request_id.in_([r.id for r in requests])
                    )
                ).all()
            )
        breaches = sum(1 for r in requests if r.status == ChangeStatus.OPEN and self.sla_breached(r))
        contingency = self.contingency_amount()
        return {
            "CHANGE_REQUESTS": Decimal(len(requests)),
            "CHANGE_APPROVAL_RATE": _ratio(len(approved), len(decided)),
            "CHANGE_REJECTION_RATE": _ratio(len(rejected), len(decided)),
            "CHANGE_AVG_CYCLE_HOURS": _avg(cycle),
            "CHANGE_AVG_IMPACT_HOURS": _avg(impact_hours),
            "CHANGE_IMPACT_COST": impact_cost,
            "CHANGE_IMPACT_DAYS": Decimal(impact_days),
            "CHANGE_EVIDENCE_COMPLETE_PCT": _ratio(len(with_evidence), len(requests)),
            "CHANGE_SLA_BREACHES": Decimal(breaches),
            "CHANGE_CONTINGENCY_CONSUMPTION": impact_cost / contingency * HUNDRED if contingency else ZERO,
        }

    def sla_breached(self, request: ChangeRequest, now: datetime | None = None) -> bool:
        active = self.session.scalar(
            sa.select(ChangeRequestStage).where(
                ChangeRequestStage.request_id == request.id,
                ChangeRequestStage.status == ChangeStageStatus.ACTIVE,
            )
        )
        if active is None or active.entered_at is None:
            return False
        stage = self.session.get(ChangeStage, active.stage_id)
        if stage is None or not stage.sla_hours:
            return False
        reference = now or project_clock(self.project)
        return reference > active.entered_at + timedelta(hours=stage.sla_hours)

    # ------------------------------------------------------------ resources
    def resource_daily_load(self) -> dict[uuid.UUID, dict[date, list[tuple[str, Decimal]]]]:
        """Hours per human resource and working day, with contributing tasks."""

        result: dict[uuid.UUID, dict[date, list[tuple[str, Decimal]]]] = defaultdict(lambda: defaultdict(list))
        for assignment in self.assignments:
            resource = self.resource_by_id.get(assignment.resource_id)
            element = self.by_id.get(assignment.element_id)
            if resource is None or element is None or resource.resource_type != ResourceType.HUMAN:
                continue
            start, finish = element.planned_start, element.planned_finish
            if start is None or finish is None:
                continue
            daily = _d(assignment.hours_per_day)
            if daily <= ZERO and element.duration_days:
                daily = _d(assignment.planned_hours) / Decimal(element.duration_days)
            current = start
            while current <= finish:
                if self.calendar.is_working_day(current, str(resource.id)):
                    result[resource.id][current].append((element.external_id, daily))
                current += timedelta(days=1)
        return result


def project_clock(project: Project | None) -> datetime:
    """Simulated "now" of a project.

    Demo projects live at their cut-off date (e.g. 15-01-2027) even if the real
    calendar is earlier.  Workflow timestamps (change requests, SLA) use this
    clock so the history stays chronological: the cut-off day at 08:00 Chile
    plus half of the seconds elapsed today (always the same calendar day).
    """

    now = datetime.now(UTC)
    if project is None or project.cutoff_date is None or project.cutoff_date <= now.date():
        return now
    midnight = datetime.combine(now.date(), time.min, tzinfo=UTC)
    return datetime.combine(project.cutoff_date, time(11, 0), tzinfo=UTC) + (now - midnight) / 2


def _calendar(session: Session, project: Project) -> BusinessCalendar:
    from app.services.persistence import project_calendar

    return project_calendar(session, project)


def _ratio(numerator: int, denominator: int) -> Decimal:
    return Decimal(numerator) / Decimal(denominator) if denominator else ZERO


def _avg(values: list[Decimal]) -> Decimal:
    return sum(values, ZERO) / Decimal(len(values)) if values else ZERO


def _min(values: Any) -> Any:
    items = [value for value in values if value is not None]
    return min(items) if items else None


def _max(values: Any) -> Any:
    items = [value for value in values if value is not None]
    return max(items) if items else None


def kpi_status(kpi_value: Decimal | None, green: Decimal | None, yellow: Decimal | None) -> str:
    """Traffic-light status; the threshold order defines the direction."""

    if kpi_value is None:
        return "SIN_DATOS"
    if green is None or yellow is None:
        return "INFO"
    value, green, yellow = _d(kpi_value), _d(green), _d(yellow)
    if green >= yellow:
        if value >= green:
            return "VERDE"
        return "AMARILLO" if value >= yellow else "ROJO"
    if value <= green:
        return "VERDE"
    return "AMARILLO" if value <= yellow else "ROJO"


def json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, list):
        return [json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    return value


__all__ = ["project_clock", "ProjectAnalytics", "ElementState", "kpi_status", "json_value", "STATUS_LABELS", "MANUAL_METRICS", "replace"]
