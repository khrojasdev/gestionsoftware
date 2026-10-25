"""Facade for the deterministic planning and cost engine."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date
from decimal import Decimal

from ..domain.models import Assignment, Resource, ScheduleResult, Task
from .calendar import BusinessCalendar
from .costs import (
    CostCalculator,
    CostReport,
    EvmCalculator,
    EvmReport,
    ResourceLoad,
    ResourceLoadCalculator,
)
from .scheduler import Scheduler


class DeterministicCalculationEngine:
    """Compose scheduling, cost, EVM and load services behind one API."""

    def __init__(self, calendar: BusinessCalendar) -> None:
        self.scheduler = Scheduler(calendar)
        self.costs = CostCalculator()
        self.evm = EvmCalculator(calendar)
        self.resource_load = ResourceLoadCalculator(calendar)

    def schedule(
        self,
        tasks: Iterable[Task],
        project_start: date | None = None,
        project_deadline: date | None = None,
    ) -> ScheduleResult:
        """Calculate dates, float, critical path and propagation changes."""

        return self.scheduler.schedule(tasks, project_start, project_deadline)

    def calculate_costs(
        self,
        tasks: Iterable[Task],
        resources: Iterable[Resource],
        assignments: Iterable[Assignment] = (),
        actual_costs: Mapping[str, Decimal] | None = None,
        weight_by: str = "cost",
    ) -> CostReport:
        """Calculate task costs and hierarchy totals."""

        return self.costs.calculate(tasks, resources, assignments, actual_costs, weight_by)

    def calculate_evm(
        self,
        tasks: Iterable[Task],
        cutoff: date,
        planned_costs: Mapping[str, Decimal] | None = None,
        actual_costs: Mapping[str, Decimal] | None = None,
    ) -> EvmReport:
        """Calculate PV, EV, AC and the standard EVM indicators."""

        return self.evm.calculate(tasks, cutoff, planned_costs, actual_costs)

    def calculate_resource_load(
        self,
        tasks: Iterable[Task],
        resources: Iterable[Resource],
        assignments: Iterable[Assignment] = (),
    ) -> tuple[ResourceLoad, ...]:
        """Calculate daily worker load and overallocations."""

        return self.resource_load.calculate(tasks, resources, assignments)
