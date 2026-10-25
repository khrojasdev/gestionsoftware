"""Cost, EVM, hierarchy consolidation and resource-load calculations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from ..domain.models import Assignment, Resource, ResourceType, Task
from .calendar import BusinessCalendar

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class TaskCost:
    task_id: str
    planned_cost: Decimal
    actual_cost: Decimal
    planned_weight: Decimal = ZERO


@dataclass(frozen=True, slots=True)
class ConsolidatedValue:
    task_id: str
    start: date | None
    finish: date | None
    planned_cost: Decimal
    actual_cost: Decimal
    progress_pct: Decimal
    planned_weight: Decimal = ZERO


@dataclass(frozen=True, slots=True)
class CostReport:
    by_task: dict[str, TaskCost]
    consolidated: dict[str, ConsolidatedValue]
    project: ConsolidatedValue


@dataclass(frozen=True, slots=True)
class EvmReport:
    bac: Decimal
    pv: Decimal
    ev: Decimal
    ac: Decimal
    spi: Decimal
    cpi: Decimal
    sv: Decimal
    cv: Decimal
    eac: Decimal
    etc: Decimal
    vac: Decimal


@dataclass(frozen=True, slots=True)
class ResourceLoad:
    resource_id: str
    day: date
    hours: Decimal
    capacity_hours: Decimal
    utilization_pct: Decimal
    overallocated: bool


class CostCalculator:
    """Calculate leaf costs and roll them up through the Gantt hierarchy."""

    def calculate(
        self,
        tasks: Iterable[Task],
        resources: Iterable[Resource],
        assignments: Iterable[Assignment] = (),
        actual_costs: Mapping[str, Decimal] | None = None,
        weight_by: str = "cost",
    ) -> CostReport:
        if weight_by not in {"cost", "hours"}:
            raise ValueError("weight_by debe ser 'cost' o 'hours'")
        task_map = {task.task_id: task for task in tasks}
        resource_map = {resource.resource_id: resource for resource in resources}
        grouped: dict[str, list[Assignment]] = {task_id: [] for task_id in task_map}
        for assignment in assignments:
            if assignment.task_id not in task_map:
                raise ValueError(f"Asignación apunta a tarea inexistente: {assignment.task_id}")
            if assignment.resource_id not in resource_map:
                raise ValueError(
                    f"Asignación apunta a recurso inexistente: {assignment.resource_id}"
                )
            grouped[assignment.task_id].append(assignment)

        by_task: dict[str, TaskCost] = {}
        for task_id, task in task_map.items():
            task_assignments = grouped[task_id] or list(task.assignments)
            planned = self._task_planned_cost(task_assignments, resource_map)
            if not task_assignments:
                planned = task.planned_cost
            actual = Decimal(str((actual_costs or {}).get(task_id, task.actual_cost or ZERO)))
            weight = self._task_weight(task_assignments, planned, weight_by)
            by_task[task_id] = TaskCost(task_id, planned, actual, weight)

        consolidated = self._consolidate(task_map, by_task)
        roots = [task_id for task_id, task in task_map.items() if task.parent_id is None]
        project = self._sum_values("PROJECT", [consolidated[root] for root in roots])
        return CostReport(by_task, consolidated, project)

    def _task_planned_cost(
        self, assignments: Iterable[Assignment], resources: Mapping[str, Resource]
    ) -> Decimal:
        total = ZERO
        for assignment in assignments:
            resource = resources[assignment.resource_id]
            if resource.resource_type == ResourceType.HUMAN:
                rate = (
                    assignment.rate_override
                    if assignment.rate_override is not None
                    else resource.rate
                )
                total += assignment.planned_hours * rate
            else:
                total += assignment.quantity * (assignment.rate_override or resource.unit_cost)
        return total

    def _task_weight(
        self,
        assignments: Iterable[Assignment],
        planned_cost: Decimal,
        weight_by: str,
    ) -> Decimal:
        if weight_by == "cost":
            return planned_cost
        return sum(
            (
                assignment.planned_hours
                if assignment.planned_hours > 0
                else assignment.quantity
            )
            for assignment in assignments
        )

    def _consolidate(
        self, tasks: Mapping[str, Task], values: Mapping[str, TaskCost]
    ) -> dict[str, ConsolidatedValue]:
        children: dict[str, list[str]] = {task_id: [] for task_id in tasks}
        for task in tasks.values():
            if task.parent_id in children:
                children[task.parent_id].append(task.task_id)

        result: dict[str, ConsolidatedValue] = {}

        def visit(task_id: str) -> ConsolidatedValue:
            task = tasks[task_id]
            child_values = [visit(child_id) for child_id in children[task_id]]
            if child_values:
                value = self._sum_values(task_id, child_values)
            else:
                planned = values[task_id].planned_cost
                actual = values[task_id].actual_cost
                value = ConsolidatedValue(
                    task_id,
                    task.start,
                    task.finish,
                    planned,
                    actual,
                    task.progress_pct,
                    values[task_id].planned_weight,
                )
            result[task_id] = value
            return value

        for task_id in tasks:
            if task_id not in result:
                visit(task_id)
        return result

    def _sum_values(self, task_id: str, values: Iterable[ConsolidatedValue]) -> ConsolidatedValue:
        items = list(values)
        planned = sum((value.planned_cost for value in items), ZERO)
        actual = sum((value.actual_cost for value in items), ZERO)
        weight = sum((value.planned_weight for value in items), ZERO)
        weighted_progress = (
            sum((value.planned_weight * value.progress_pct for value in items), ZERO) / weight
            if weight
            else ZERO
        )
        starts = [value.start for value in items if value.start is not None]
        finishes = [value.finish for value in items if value.finish is not None]
        return ConsolidatedValue(
            task_id,
            min(starts) if starts else None,
            max(finishes) if finishes else None,
            planned,
            actual,
            weighted_progress,
            weight,
        )


class EvmCalculator:
    """Earned-value metrics using exact Decimal arithmetic."""

    def __init__(self, calendar: BusinessCalendar) -> None:
        self.calendar = calendar

    def calculate(
        self,
        tasks: Iterable[Task],
        cutoff: date,
        planned_costs: Mapping[str, Decimal] | None = None,
        actual_costs: Mapping[str, Decimal] | None = None,
    ) -> EvmReport:
        task_list = list(tasks)
        planned = planned_costs or {task.task_id: task.planned_cost for task in task_list}
        actual = actual_costs or {
            task.task_id: task.actual_cost or ZERO for task in task_list
        }
        bac = sum((Decimal(str(planned.get(task.task_id, ZERO))) for task in task_list), ZERO)
        pv = sum(
            (
                Decimal(str(planned.get(task.task_id, ZERO)))
                * self._planned_pct(task, cutoff)
                for task in task_list
            ),
            ZERO,
        )
        ev = sum(
            (
                Decimal(str(planned.get(task.task_id, ZERO)))
                * self._actual_pct(task)
                for task in task_list
            ),
            ZERO,
        )
        ac = sum((Decimal(str(actual.get(task.task_id, ZERO))) for task in task_list), ZERO)
        spi = ev / pv if pv else ZERO
        cpi = ev / ac if ac else ZERO
        eac = bac / cpi if cpi else bac
        return EvmReport(bac, pv, ev, ac, spi, cpi, ev - pv, ev - ac, eac, eac - ac, bac - eac)

    def _planned_pct(self, task: Task, cutoff: date) -> Decimal:
        if task.start is None or task.duration_days is None:
            return Decimal("1") if task.finish is not None and cutoff >= task.finish else ZERO
        finish = task.finish or self.calendar.duration_finish(task.start, task.duration_days)
        if task.duration_days == 0:
            return Decimal("1") if cutoff >= finish else ZERO
        if cutoff < task.start:
            return ZERO
        if cutoff >= finish:
            return Decimal("1")
        elapsed = self.calendar.working_days_inclusive(task.start, cutoff)
        return min(Decimal("1"), Decimal(elapsed) / Decimal(task.duration_days))

    @staticmethod
    def _actual_pct(task: Task) -> Decimal:
        return max(ZERO, min(Decimal("1"), task.progress_pct / Decimal("100")))


class ResourceLoadCalculator:
    """Expand assignments to daily load and mark overallocations."""

    def __init__(self, calendar: BusinessCalendar) -> None:
        self.calendar = calendar

    def calculate(
        self,
        tasks: Iterable[Task],
        resources: Iterable[Resource],
        assignments: Iterable[Assignment] = (),
    ) -> tuple[ResourceLoad, ...]:
        task_map = {task.task_id: task for task in tasks}
        resource_map = {resource.resource_id: resource for resource in resources}
        loads: dict[tuple[str, date], Decimal] = {}
        assignment_list = list(assignments)
        if not assignment_list:
            assignment_list = [
                assignment
                for task in task_map.values()
                for assignment in task.assignments
            ]
        for assignment in assignment_list:
            task = task_map[assignment.task_id]
            resource = resource_map[assignment.resource_id]
            if task.start is None:
                continue
            finish = task.finish or self.calendar.duration_finish(
                task.start,
                task.duration_days or 0,
                resource.resource_id,
            )
            daily = assignment.hours_per_day
            if daily <= 0 and assignment.planned_hours > 0 and task.duration_days:
                daily = assignment.planned_hours / Decimal(task.duration_days)
            current = task.start
            while current <= finish:
                if self.calendar.is_working_day(current, resource.resource_id):
                    key = (resource.resource_id, current)
                    loads[key] = loads.get(key, ZERO) + daily
                current += timedelta(days=1)
        result: list[ResourceLoad] = []
        for (resource_id, day), hours in sorted(
            loads.items(), key=lambda item: (item[0][0], item[0][1])
        ):
            capacity = resource_map[resource_id].capacity_hours_per_day
            utilization = (hours / capacity * Decimal("100")) if capacity else ZERO
            result.append(
                ResourceLoad(
                    resource_id,
                    day,
                    hours,
                    capacity,
                    utilization,
                    hours > capacity,
                )
            )
        return tuple(result)
