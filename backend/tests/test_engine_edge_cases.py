from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domain.models import Assignment, Dependency, Resource, ResourceType, Task
from app.services.calendar import BusinessCalendar, chilean_holidays
from app.services.costs import CostCalculator, EvmCalculator, ResourceLoadCalculator
from app.services.f7 import ImpactAnalyzer, TaskUpdate
from app.services.calculation_engine import DeterministicCalculationEngine
from app.services.scheduler import CycleError, ScheduleError, Scheduler, parse_predecessors


MONDAY = date(2026, 10, 5)


def make_task(task_id: str, duration: int, **kwargs: object) -> Task:
    return Task(task_id, duration_days=duration, **kwargs)


@pytest.mark.parametrize(
    ("relation", "lag", "expected_start"),
    [
        ("FS", 2, date(2026, 10, 9)),
        ("FS", -1, date(2026, 10, 6)),
        ("SS", 2, date(2026, 10, 7)),
        ("SS", -1, date(2026, 10, 5)),
        ("FF", 1, date(2026, 10, 6)),
        ("FF", -1, date(2026, 10, 5)),
        ("SF", 1, date(2026, 10, 5)),
        ("SF", -1, date(2026, 10, 5)),
    ],
)
def test_dependency_lags_are_applied_for_each_precedence_type(
    relation: str, lag: int, expected_start: date
) -> None:
    result = Scheduler(BusinessCalendar()).schedule(
        [
            make_task("A", 2, start=MONDAY),
            make_task("B", 2, predecessors=(Dependency("A", relation, lag),)),
        ],
        project_start=MONDAY,
    )

    assert result.tasks["B"].start == expected_start


def test_dependency_lag_skips_weekends_and_project_holidays() -> None:
    calendar = BusinessCalendar(holidays={date(2026, 10, 12)})
    result = Scheduler(calendar).schedule(
        [
            make_task("A", 1, start=date(2026, 10, 9)),
            make_task("B", 1, predecessors=(Dependency("A", "FS", 0),)),
        ],
        project_start=date(2026, 10, 9),
    )

    assert result.tasks["A"].finish == date(2026, 10, 9)
    assert result.tasks["B"].start == date(2026, 10, 13)


def test_chilean_calendar_handles_movable_holidays_and_signed_distances() -> None:
    holidays = chilean_holidays(2026)
    calendar = BusinessCalendar.chile([2026])

    assert date(2026, 4, 3) in holidays  # Viernes Santo
    assert date(2026, 4, 4) in holidays  # Sábado Santo
    assert calendar.is_working_day(date(2026, 4, 2))
    assert not calendar.is_working_day(date(2026, 4, 3))
    assert calendar.next_working_day(date(2026, 4, 3)) == date(2026, 4, 6)
    assert calendar.previous_working_day(date(2026, 4, 5)) == date(2026, 4, 2)
    assert calendar.add_working_days(date(2026, 4, 6), -1) == date(2026, 4, 2)
    assert calendar.working_days_between(date(2026, 4, 6), date(2026, 4, 2)) == -1
    assert calendar.working_days_inclusive(date(2026, 4, 6), date(2026, 4, 2)) == 0

    with pytest.raises(ValueError, match="no puede ser negativa"):
        calendar.duration_finish(MONDAY, -1)


def test_scheduler_rejects_empty_graph_missing_predecessor_and_negative_duration() -> None:
    scheduler = Scheduler(BusinessCalendar())

    with pytest.raises(ScheduleError, match="no puede estar vacío"):
        scheduler.schedule([], project_start=MONDAY)
    with pytest.raises(ScheduleError, match="Predecesora inexistente"):
        scheduler.schedule([make_task("B", 1, predecessors=(Dependency("A"),))], project_start=MONDAY)
    with pytest.raises(ScheduleError, match="Duración inválida"):
        scheduler.schedule([make_task("A", -1)], project_start=MONDAY)


def test_cycle_error_contains_the_complete_cycle_chain() -> None:
    tasks = [
        make_task("A", 1, predecessors=(Dependency("C"),)),
        make_task("B", 1, predecessors=(Dependency("A"),)),
        make_task("C", 1, predecessors=(Dependency("B"),)),
    ]

    with pytest.raises(CycleError, match="A → C → B → A"):
        Scheduler(BusinessCalendar()).schedule(tasks, project_start=MONDAY)


def test_propagation_records_changed_successors_after_duration_update() -> None:
    tasks = [
        make_task("A", 1, start=MONDAY),
        make_task("B", 1, predecessors=(Dependency("A"),)),
        make_task("C", 1, predecessors=(Dependency("B"),)),
    ]
    initial = Scheduler(BusinessCalendar()).schedule(tasks, project_start=MONDAY)
    initial.tasks["A"].duration_days = 3
    updated = Scheduler(BusinessCalendar()).schedule(initial.tasks.values(), project_start=MONDAY)

    assert updated.tasks["B"].start == date(2026, 10, 8)
    assert updated.tasks["C"].start == date(2026, 10, 9)
    assert {change.task_id for change in updated.changes} == {"A", "B", "C"}


def test_consolidation_rolls_up_cost_actuals_and_hour_weights() -> None:
    resources = [Resource("dev", resource_type=ResourceType.HUMAN, rate=Decimal("10"))]
    assignments = [
        Assignment("A", "dev", planned_hours=Decimal("3"), hours_per_day=Decimal("3")),
        Assignment("B", "dev", planned_hours=Decimal("2"), hours_per_day=Decimal("2")),
    ]
    tasks = [
        make_task("stage", 1, kind="ETAPA", parent_id=None),
        make_task("A", 1, parent_id="stage", start=MONDAY, progress_pct=Decimal("100"), actual_cost=5),
        make_task("B", 1, parent_id="stage", start=date(2026, 10, 6), progress_pct=Decimal("50"), actual_cost=7),
    ]

    report = CostCalculator().calculate(tasks, resources, assignments, weight_by="hours")

    assert report.by_task["A"].planned_cost == Decimal("30")
    assert report.by_task["B"].planned_cost == Decimal("20")
    assert report.consolidated["stage"].planned_cost == Decimal("50")
    assert report.consolidated["stage"].actual_cost == Decimal("12")
    assert report.consolidated["stage"].progress_pct == Decimal("80")
    assert report.project.planned_cost == Decimal("50")


def test_evm_handles_partial_progress_and_zero_divisors_exactly() -> None:
    calendar = BusinessCalendar(holidays={date(2026, 10, 12)})
    task = make_task(
        "A", 3, start=date(2026, 10, 9), planned_cost=Decimal("100"), progress_pct=50, actual_cost=60
    )
    evm = EvmCalculator(calendar).calculate([task], date(2026, 10, 12))

    assert evm.bac == Decimal("100")
    assert evm.pv == Decimal("100") / Decimal("3")
    assert evm.ev == Decimal("50")
    assert evm.ac == Decimal("60")
    assert evm.spi == Decimal("1.5")
    assert evm.cpi == Decimal("0.8333333333333333333333333333")
    assert evm.vac == Decimal("-20")

    zero = EvmCalculator(calendar).calculate([make_task("empty", 1)], MONDAY)
    assert zero.spi == Decimal("0")
    assert zero.cpi == Decimal("0")
    assert zero.eac == Decimal("0")


def test_resource_load_marks_overallocation_and_resource_holiday() -> None:
    calendar = BusinessCalendar(resource_exceptions={"worker": {date(2026, 10, 6)}})
    resource = Resource("worker", capacity_hours_per_day=Decimal("8"))
    tasks = [make_task("A", 2, start=MONDAY), make_task("B", 2, start=MONDAY)]
    assignments = [
        Assignment("A", "worker", hours_per_day=Decimal("6")),
        Assignment("B", "worker", hours_per_day=Decimal("4")),
    ]

    loads = ResourceLoadCalculator(calendar).calculate(tasks, [resource], assignments)

    assert [load.day for load in loads] == [MONDAY, date(2026, 10, 7)]
    assert loads[0].hours == Decimal("10")
    assert loads[0].overallocated is True
    assert loads[1].hours == Decimal("10")


def test_parser_rejects_malformed_dependency_without_evaluating_input() -> None:
    assert parse_predecessors("A16; A10SS+2; A05FF-1") == (
        Dependency("A16"),
        Dependency("A10", "SS", 2),
        Dependency("A05", "FF", -1),
    )
    with pytest.raises(ScheduleError, match="Predecesora inválida"):
        parse_predecessors("__import__('os').system('whoami')")


def test_demo_scenario_one_duration_change_propagates_to_hito() -> None:
    engine = DeterministicCalculationEngine(BusinessCalendar())
    tasks = [
        make_task("A02", 4, start=MONDAY, planned_cost=100),
        make_task("H01", 0, predecessors=(Dependency("A02"),), planned_cost=0),
    ]
    baseline = engine.schedule(tasks, project_start=MONDAY)
    proposal = [make_task("A02", 6, start=MONDAY, planned_cost=100), tasks[1]]
    changed = engine.schedule(proposal, project_start=MONDAY)

    assert baseline.tasks["H01"].finish == date(2026, 10, 9)
    assert changed.tasks["H01"].finish == date(2026, 10, 13)


def test_demo_scenario_two_resource_replacement_changes_consolidated_cost() -> None:
    calendar = BusinessCalendar()
    task = make_task("A05", 1, start=MONDAY, parent_id="stage")
    stage = make_task("stage", 1, kind="ETAPA")
    old = Resource("R001", resource_type=ResourceType.HUMAN, rate=Decimal("100"))
    replacement = Resource("R003", resource_type=ResourceType.HUMAN, rate=Decimal("150"))

    before = CostCalculator().calculate([stage, task], [old], [Assignment("A05", "R001", planned_hours=2)])
    after = CostCalculator().calculate([stage, task], [replacement], [Assignment("A05", "R003", planned_hours=2)])

    assert before.consolidated["stage"].planned_cost == Decimal("200")
    assert after.consolidated["stage"].planned_cost == Decimal("300")
    assert after.project.planned_cost - before.project.planned_cost == Decimal("100")
    assert calendar.is_working_day(MONDAY)


def test_demo_scenario_three_change_impact_isolated_and_tracks_contingency() -> None:
    engine = DeterministicCalculationEngine(BusinessCalendar())
    analyzer = ImpactAnalyzer(engine)
    task = make_task("CR-002-TASK", 2, start=MONDAY, planned_cost=Decimal("350"))

    result = analyzer.simulate(
        [task], [], updates=[TaskUpdate("CR-002-TASK", duration_days=4, planned_cost=Decimal("500"))],
        project_start=MONDAY, contingency_pct=Decimal("10"),
    )

    assert result.delta_cost == Decimal("150")
    assert result.delta_contingency == Decimal("15")
    assert result.proposed_finish > result.baseline_finish
    assert task.duration_days == 2
    assert task.planned_cost == Decimal("350")


def test_calculation_engine_facade_delegates_evm_and_load_operations() -> None:
    engine = DeterministicCalculationEngine(BusinessCalendar())
    task = make_task("A", 1, start=MONDAY, planned_cost=Decimal("10"), progress_pct=100)
    resource = Resource("worker", rate=Decimal("10"), capacity_hours_per_day=Decimal("8"))
    assignment = Assignment("A", "worker", planned_hours=Decimal("1"), hours_per_day=Decimal("1"))

    evm = engine.calculate_evm([task], MONDAY)
    loads = engine.calculate_resource_load([task], [resource], [assignment])

    assert evm.bac == Decimal("10")
    assert loads[0].hours == Decimal("1")
