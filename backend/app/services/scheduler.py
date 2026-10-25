"""Deterministic precedence scheduler (forward/backward pass)."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import replace
from datetime import date

from ..domain.models import ChangeRecord, Dependency, ScheduleResult, Task
from .calendar import BusinessCalendar


class ScheduleError(ValueError):
    """Invalid scheduling input."""


class CycleError(ScheduleError):
    """A precedence graph contains a cycle."""

    def __init__(self, cycle: tuple[str, ...]) -> None:
        self.cycle = cycle
        super().__init__(f"Ciclo detectado: {' → '.join(cycle)}")


_PRED_RE = re.compile(r"^\s*([A-Za-z0-9_-]+?)(FS|SS|FF|SF)?([+-]\d+)?\s*$")


def parse_predecessors(value: str | None) -> tuple[Dependency, ...]:
    """Parse ``A16; A10SS+2; A05FF-1`` without evaluating user input."""

    if not value or not value.strip():
        return ()
    dependencies: list[Dependency] = []
    for token in value.split(";"):
        match = _PRED_RE.fullmatch(token)
        if match is None:
            raise ScheduleError(f"Predecesora inválida: {token.strip()}")
        predecessor_id, dependency_type, lag = match.groups()
        dependencies.append(Dependency(predecessor_id, dependency_type or "FS", int(lag or 0)))
    return tuple(dependencies)


class Scheduler:
    """Schedules a graph using only calendar and precedence rules."""

    def __init__(self, calendar: BusinessCalendar) -> None:
        self.calendar = calendar

    def schedule(
        self,
        tasks: Iterable[Task],
        project_start: date | None = None,
        project_deadline: date | None = None,
    ) -> ScheduleResult:
        """Run forward/backward passes and return all changed task values."""

        task_map = {task.task_id: replace(task) for task in tasks}
        self._validate(task_map)
        order = self._topological_order(task_map)
        self._derive_durations(task_map)
        inferred_start = self._infer_project_start(task_map)
        start_anchor = project_start or inferred_start
        if start_anchor is None:
            raise ScheduleError("Se requiere project_start cuando no hay fechas iniciales")

        before = {task_id: self._snapshot(task) for task_id, task in task_map.items()}
        for task_id in order:
            task = task_map[task_id]
            base_start = self._base_start(task, start_anchor)
            candidate_starts = [base_start]
            for dependency in task.predecessors:
                predecessor = task_map[dependency.predecessor_id]
                candidate_starts.append(self._successor_start(predecessor, task, dependency))
            task.start = max(candidate_starts)
            task.finish = self.calendar.duration_finish(task.start, task.duration_days or 0)

        calculated_finish = max(
            task.finish for task in task_map.values() if task.finish is not None
        )
        deadline = project_deadline or calculated_finish
        latest_start = self._backward_pass(task_map, order, deadline)
        successors = self._successors(task_map)
        for task_id, task in task_map.items():
            task.total_slack_days = self.calendar.working_days_between(
                task.start, latest_start[task_id]
            )
            task.free_slack_days = self._free_slack(task, task_map, successors[task_id])
            task.critical = task.total_slack_days == 0

        changes = tuple(
            ChangeRecord(task_id, before[task_id], self._snapshot(task))
            for task_id, task in task_map.items()
            if before[task_id] != self._snapshot(task)
        )
        final_finish = max(task.finish for task in task_map.values() if task.finish is not None)
        return ScheduleResult(
            task_map,
            min(task.start for task in task_map.values() if task.start),
            final_finish,
            changes,
        )

    def validate_graph(self, tasks: Iterable[Task]) -> None:
        """Validate references and cycles without requiring task durations."""

        task_map = {task.task_id: task for task in tasks}
        self._validate(task_map)
        self._topological_order(task_map)

    def _validate(self, tasks: Mapping[str, Task]) -> None:
        if len(tasks) == 0:
            raise ScheduleError("El cronograma no puede estar vacío")
        for task in tasks.values():
            for dependency in task.predecessors:
                if dependency.predecessor_id not in tasks:
                    raise ScheduleError(f"Predecesora inexistente: {dependency.predecessor_id}")
            if task.duration_days is not None and task.duration_days < 0:
                raise ScheduleError(f"Duración inválida en {task.task_id}")

    def _derive_durations(self, tasks: Mapping[str, Task]) -> None:
        for task in tasks.values():
            if task.effort_hours is None:
                if task.duration_days is None:
                    raise ScheduleError(f"Falta duración en {task.task_id}")
                continue
            daily_total = sum(
                assignment.hours_per_day
                for assignment in task.assignments
                if assignment.hours_per_day > 0
            )
            if daily_total <= 0:
                raise ScheduleError(f"No hay dedicación diaria para el esfuerzo de {task.task_id}")
            rounded_days = (task.effort_hours / daily_total).to_integral_value(
                rounding="ROUND_CEILING"
            )
            task.duration_days = max(1, int(rounded_days))

    def _infer_project_start(self, tasks: Mapping[str, Task]) -> date | None:
        starts = [task.start for task in tasks.values() if task.start is not None]
        finishes = [
            task.finish
            for task in tasks.values()
            if task.finish is not None and task.start is None
        ]
        if starts:
            return min(starts)
        return min(finishes) if finishes else None

    def _base_start(self, task: Task, project_start: date) -> date:
        if task.start is not None:
            return self.calendar.next_working_day(task.start)
        if task.finish is not None:
            return self._start_from_finish(task.finish, task.duration_days or 0)
        return self.calendar.next_working_day(project_start)

    def _successor_start(self, predecessor: Task, successor: Task, dependency: Dependency) -> date:
        relation = dependency.dependency_type
        if relation == "FS":
            return self.calendar.add_working_days(predecessor.finish, 1 + dependency.lag_days)
        if relation == "SS":
            return self.calendar.add_working_days(predecessor.start, dependency.lag_days)
        if relation == "FF":
            finish = self.calendar.add_working_days(predecessor.finish, dependency.lag_days)
            return self._start_from_finish(finish, successor.duration_days or 0)
        finish = self.calendar.add_working_days(predecessor.start, dependency.lag_days)
        return self._start_from_finish(finish, successor.duration_days or 0)

    def _backward_pass(
        self, tasks: Mapping[str, Task], order: list[str], deadline: date
    ) -> dict[str, date]:
        successors = self._successors(tasks)
        latest: dict[str, date] = {}
        for task_id in reversed(order):
            task = tasks[task_id]
            candidate_starts = [
                self._start_from_finish(deadline, task.duration_days or 0)
            ] if not successors[task_id] else []
            for successor_id, dependency in successors[task_id]:
                successor = tasks[successor_id]
                if dependency.dependency_type == "FS":
                    bound_finish = self.calendar.add_working_days(
                        latest[successor_id], -(1 + dependency.lag_days)
                    )
                    candidate_starts.append(
                        self._start_from_finish(bound_finish, task.duration_days or 0)
                    )
                elif dependency.dependency_type == "SS":
                    candidate_starts.append(
                        self.calendar.add_working_days(
                            latest[successor_id], -dependency.lag_days
                        )
                    )
                elif dependency.dependency_type == "FF":
                    successor_finish = self.calendar.duration_finish(
                        latest[successor_id], successor.duration_days or 0
                    )
                    candidate_starts.append(
                        self._start_from_finish(
                            self.calendar.add_working_days(successor_finish, -dependency.lag_days),
                            task.duration_days or 0,
                        )
                    )
                else:  # SF: successor finish >= predecessor start + lag
                    successor_finish = self.calendar.duration_finish(
                        latest[successor_id], successor.duration_days or 0
                    )
                    candidate_starts.append(
                        self.calendar.add_working_days(successor_finish, -dependency.lag_days)
                    )
            latest[task_id] = min(candidate_starts)
        return latest

    def _successors(self, tasks: Mapping[str, Task]) -> dict[str, list[tuple[str, Dependency]]]:
        result = {task_id: [] for task_id in tasks}
        for successor in tasks.values():
            for dependency in successor.predecessors:
                result[dependency.predecessor_id].append((successor.task_id, dependency))
        return result

    def _free_slack(
        self, task: Task, tasks: Mapping[str, Task], successors: list[tuple[str, Dependency]]
    ) -> int:
        if not successors:
            return task.total_slack_days or 0
        values: list[int] = []
        for successor_id, dependency in successors:
            successor = tasks[successor_id]
            if dependency.dependency_type in {"FS", "SS"}:
                required = self._successor_start(task, successor, dependency)
                values.append(self.calendar.working_days_between(required, successor.start))
            elif dependency.dependency_type == "FF":
                required = self.calendar.add_working_days(task.finish, dependency.lag_days)
                values.append(self.calendar.working_days_between(required, successor.finish))
            else:
                required = self.calendar.add_working_days(task.start, dependency.lag_days)
                values.append(self.calendar.working_days_between(required, successor.finish))
        return min(values)

    def _topological_order(self, tasks: Mapping[str, Task]) -> list[str]:
        state: dict[str, int] = {task_id: 0 for task_id in tasks}
        order: list[str] = []
        path: list[str] = []

        def visit(task_id: str) -> None:
            if state[task_id] == 1:
                cycle_start = path.index(task_id)
                raise CycleError(tuple(path[cycle_start:] + [task_id]))
            if state[task_id] == 2:
                return
            state[task_id] = 1
            path.append(task_id)
            for dependency in tasks[task_id].predecessors:
                visit(dependency.predecessor_id)
            path.pop()
            state[task_id] = 2
            order.append(task_id)

        for task_id in tasks:
            visit(task_id)
        return order

    @staticmethod
    def _snapshot(task: Task) -> dict[str, object]:
        return {
            "start": task.start,
            "finish": task.finish,
            "duration_days": task.duration_days,
            "total_slack_days": task.total_slack_days,
            "free_slack_days": task.free_slack_days,
            "critical": task.critical,
        }

    def _start_from_finish(self, finish: date, duration_days: int) -> date:
        """Invert an inclusive duration, including zero-duration milestones."""

        return self.calendar.add_working_days(finish, -max(duration_days - 1, 0))
