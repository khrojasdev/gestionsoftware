"""Typed, persistence-independent models for scheduling and cost calculations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum


class ResourceType(StrEnum):
    """Supported resource categories from the Carta Gantt template."""

    HUMAN = "HUMANO"
    EQUIPMENT = "EQUIPAMIENTO"
    INFRASTRUCTURE_LICENSE = "INFRAESTRUCTURA_LICENCIA"
    EXTERNAL_SERVICE = "SERVICIO_EXTERNO"


@dataclass(frozen=True, slots=True)
class Dependency:
    """A directed predecessor relationship."""

    predecessor_id: str
    dependency_type: str = "FS"
    lag_days: int = 0

    def __post_init__(self) -> None:
        dependency_type = self.dependency_type.upper()
        if dependency_type not in {"FS", "SS", "FF", "SF"}:
            raise ValueError(f"Tipo de dependencia inválido: {self.dependency_type}")
        object.__setattr__(self, "dependency_type", dependency_type)


@dataclass(slots=True)
class Assignment:
    """A task-resource allocation."""

    task_id: str
    resource_id: str
    planned_hours: Decimal = Decimal("0")
    quantity: Decimal = Decimal("0")
    hours_per_day: Decimal = Decimal("0")
    rate_override: Decimal | None = None

    def __post_init__(self) -> None:
        self.planned_hours = Decimal(str(self.planned_hours))
        self.quantity = Decimal(str(self.quantity))
        self.hours_per_day = Decimal(str(self.hours_per_day))
        if self.rate_override is not None:
            self.rate_override = Decimal(str(self.rate_override))


@dataclass(slots=True)
class Resource:
    """A human or non-human cost/load resource."""

    resource_id: str
    name: str = ""
    resource_type: ResourceType = ResourceType.HUMAN
    rate: Decimal = Decimal("0")
    unit_cost: Decimal = Decimal("0")
    capacity_hours_per_day: Decimal = Decimal("8")

    def __post_init__(self) -> None:
        if isinstance(self.resource_type, str):
            self.resource_type = ResourceType(self.resource_type.upper())
        self.rate = Decimal(str(self.rate))
        self.unit_cost = Decimal(str(self.unit_cost))
        self.capacity_hours_per_day = Decimal(str(self.capacity_hours_per_day))


@dataclass(slots=True)
class Task:
    """A schedulable Gantt element.

    Parent rows (stages and activities) can omit dates and duration; the
    consolidation service derives them from their children.
    """

    task_id: str
    name: str = ""
    kind: str = "SUBACTIVIDAD"
    parent_id: str | None = None
    start: date | None = None
    finish: date | None = None
    duration_days: int | None = None
    predecessors: tuple[Dependency, ...] = field(default_factory=tuple)
    effort_hours: Decimal | None = None
    progress_pct: Decimal = Decimal("0")
    actual_start: date | None = None
    actual_finish: date | None = None
    actual_cost: Decimal | None = None
    planned_cost: Decimal = Decimal("0")
    total_slack_days: int | None = None
    free_slack_days: int | None = None
    critical: bool = False
    assignments: tuple[Assignment, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        self.kind = self.kind.upper()
        self.progress_pct = Decimal(str(self.progress_pct))
        self.planned_cost = Decimal(str(self.planned_cost))
        if self.effort_hours is not None:
            self.effort_hours = Decimal(str(self.effort_hours))
        if self.actual_cost is not None:
            self.actual_cost = Decimal(str(self.actual_cost))
        self.predecessors = tuple(self.predecessors)
        self.assignments = tuple(self.assignments)


@dataclass(frozen=True, slots=True)
class ChangeRecord:
    """Before/after data returned by a propagation operation."""

    task_id: str
    before: dict[str, object]
    after: dict[str, object]


@dataclass(slots=True)
class ScheduleResult:
    """Output of a deterministic forward/backward scheduling pass."""

    tasks: dict[str, Task]
    project_start: date
    project_finish: date
    changes: tuple[ChangeRecord, ...] = field(default_factory=tuple)
