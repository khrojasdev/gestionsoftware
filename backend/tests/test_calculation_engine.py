from datetime import date
from decimal import Decimal

import pytest

from app.domain.models import Assignment, Dependency, Resource, ResourceType, Task
from app.services.calendar import BusinessCalendar
from app.services.costs import CostCalculator, EvmCalculator, ResourceLoadCalculator
from app.services.scheduler import CycleError, Scheduler, parse_predecessors


MONDAY = date(2026, 10, 5)


def task(task_id: str, duration: int, **kwargs: object) -> Task:
    return Task(task_id, duration_days=duration, **kwargs)


@pytest.mark.parametrize(
    ("relation", "expected_start"),
    [("FS", date(2026, 10, 7)), ("SS", MONDAY), ("FF", MONDAY), ("SF", MONDAY)],
)
def test_all_precedence_types(relation: str, expected_start: date) -> None:
    calendar = BusinessCalendar()
    tasks = [
        task("A", 2, start=MONDAY),
        task("B", 2, predecessors=(Dependency("A", relation),)),
    ]

    result = Scheduler(calendar).schedule(tasks, project_start=MONDAY)

    assert result.tasks["B"].start == expected_start


def test_fs_positive_and_negative_lag() -> None:
    calendar = BusinessCalendar()
    base = task("A", 2, start=MONDAY)
    positive = task("B", 1, predecessors=(Dependency("A", "FS", 1),))
    negative = task("C", 1, predecessors=(Dependency("A", "FS", -1),))

    result = Scheduler(calendar).schedule([base, positive, negative], project_start=MONDAY)

    assert result.tasks["B"].start == date(2026, 10, 8)
    assert result.tasks["C"].start == date(2026, 10, 6)


def test_holiday_is_skipped() -> None:
    calendar = BusinessCalendar(holidays={date(2026, 10, 12)})
    result = Scheduler(calendar).schedule([task("A", 2, start=date(2026, 10, 9))])

    assert result.tasks["A"].finish == date(2026, 10, 13)


def test_cycle_reports_exact_chain() -> None:
    tasks = [
        task("A", 1, predecessors=(Dependency("C"),)),
        task("B", 1, predecessors=(Dependency("A"),)),
        task("C", 1, predecessors=(Dependency("B"),)),
    ]

    with pytest.raises(CycleError, match="A → C → B → A"):
        Scheduler(BusinessCalendar()).schedule(tasks, project_start=MONDAY)


def test_propagation_returns_before_after_records() -> None:
    tasks = [
        task("A", 1, start=MONDAY),
        task("B", 1, predecessors=(Dependency("A"),)),
    ]
    first = Scheduler(BusinessCalendar()).schedule(tasks, project_start=MONDAY)
    first.tasks["A"].duration_days = 2

    second = Scheduler(BusinessCalendar()).schedule(first.tasks.values(), project_start=MONDAY)

    changed = {change.task_id for change in second.changes}
    assert changed == {"A", "B"}
    assert second.tasks["B"].start == date(2026, 10, 7)


def test_consolidation_and_costs() -> None:
    resources = [Resource("dev", resource_type=ResourceType.HUMAN, rate=Decimal("10"))]
    assignments = [
        Assignment("A", "dev", planned_hours=Decimal("3"), hours_per_day=Decimal("3")),
        Assignment("B", "dev", planned_hours=Decimal("2"), hours_per_day=Decimal("2")),
    ]
    tasks = [
        task("stage", 1, kind="ETAPA", parent_id=None, progress_pct=Decimal("0")),
        task("A", 1, parent_id="stage", start=MONDAY, progress_pct=Decimal("100")),
        task("B", 1, parent_id="stage", start=date(2026, 10, 6), progress_pct=Decimal("50")),
    ]

    report = CostCalculator().calculate(tasks, resources, assignments)

    assert report.by_task["A"].planned_cost == Decimal("30")
    assert report.consolidated["stage"].planned_cost == Decimal("50")
    assert report.consolidated["stage"].progress_pct == Decimal("80")


def test_evm_exact_metrics() -> None:
    calendar = BusinessCalendar()
    tasks = [
        task("A", 2, start=MONDAY, planned_cost=Decimal("100"), progress_pct=Decimal("50"), actual_cost=Decimal("60")),
    ]

    evm = EvmCalculator(calendar).calculate(tasks, date(2026, 10, 5))

    assert evm.bac == Decimal("100")
    assert evm.pv == Decimal("50")
    assert evm.ev == Decimal("50")
    assert evm.ac == Decimal("60")
    assert evm.spi == Decimal("1")
    assert evm.cpi == Decimal("0.8333333333333333333333333333")
    assert evm.sv == Decimal("0")
    assert evm.cv == Decimal("-10")


def test_resource_overallocation() -> None:
    calendar = BusinessCalendar()
    resource = Resource("worker", capacity_hours_per_day=Decimal("8"))
    tasks = [task("A", 1, start=MONDAY), task("B", 1, start=MONDAY)]
    assignments = [
        Assignment("A", "worker", hours_per_day=Decimal("6")),
        Assignment("B", "worker", hours_per_day=Decimal("4")),
    ]

    loads = ResourceLoadCalculator(calendar).calculate(tasks, [resource], assignments)

    assert loads[0].hours == Decimal("10")
    assert loads[0].overallocated is True


def test_predecessor_parser_is_not_eval_based() -> None:
    assert parse_predecessors("A16; A10SS+2; A05FF-1") == (
        Dependency("A16"),
        Dependency("A10", "SS", 2),
        Dependency("A05", "FF", -1),
    )
