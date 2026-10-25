from __future__ import annotations

from datetime import date

from app.domain.models import Task
from app.services.calendar import BusinessCalendar
from app.services.calculation_engine import DeterministicCalculationEngine
from app.services.f7 import ImpactAnalyzer, TaskUpdate
from trazo_importer.models import CanonicalWorkbook
from trazo_importer.service import InMemoryImportStore
from trazo_importer.template import template_sheets


def test_what_if_schedules_leaf_graph_without_parent_durations() -> None:
    tasks = [
        Task("stage", kind="ETAPA"),
        Task("activity", kind="ACTIVIDAD", parent_id="stage"),
        Task("leaf", kind="SUBACTIVIDAD", parent_id="activity", start=date(2026, 10, 5), duration_days=2),
    ]

    result = ImpactAnalyzer(DeterministicCalculationEngine(BusinessCalendar())).simulate(
        tasks,
        [],
        updates=[TaskUpdate("leaf", duration_days=3)],
        project_start=date(2026, 10, 5),
    )

    assert result.proposed_finish > result.baseline_finish
    assert tasks[0].duration_days is None


def test_in_memory_reimports_receive_monotonic_baseline_versions() -> None:
    store = InMemoryImportStore()
    workbook = CanonicalWorkbook(template_sheets())
    store.commit_import(workbook)
    first = store.baseline_version
    store.commit_import(workbook)
    second = store.baseline_version

    assert first == "v1.0"
    assert second == "v2.0"
