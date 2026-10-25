"""Application services that join persistence with the existing domain engine."""

from __future__ import annotations

import uuid
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.models import (
    AcceptanceCriterion,
    ActualCost,
    Assignment as DbAssignment,
    Baseline,
    BaselineElement,
    BaselineStatus,
    CalendarEntry,
    CalendarDayType,
    ChangePriority,
    ChangeRequest,
    ChangeRequestStage,
    ChangeStage,
    ChangeStageStatus,
    ChangeStatus,
    ChangeType,
    Dependency as DbDependency,
    GanttElement,
    GanttElementType,
    Dashboard,
    Kpi,
    KpiScope,
    Milestone,
    MilestoneTask,
    Project,
    ProjectStatus,
    ProgressRecord,
    Resource as DbResource,
    ResourceType,
    utc_now,
)
from app.services.calendar import BusinessCalendar
from app.services.calculation_engine import DeterministicCalculationEngine
from app.services.scheduler import parse_predecessors
from app.services.costs import CostCalculator
from trazo_importer.models import CanonicalWorkbook, ImportResult
from trazo_importer.service import ImportService

from app.domain.models import Assignment, Dependency, Resource, Task


def require_project(session: Session, project_id: uuid.UUID) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise ApiError("NOT_FOUND", "Proyecto no encontrado", 404)
    return project


def project_calendar(session: Session, project: Project) -> BusinessCalendar:
    entries = session.scalars(
        sa.select(CalendarEntry).where(CalendarEntry.project_id == project.id)
    ).all()
    holidays = {entry.calendar_date for entry in entries if entry.day_type != CalendarDayType.RESOURCE_EXCEPTION}
    exceptions: dict[str, list[date]] = {}
    for entry in entries:
        if entry.resource_id is not None and entry.day_type == CalendarDayType.RESOURCE_EXCEPTION:
            exceptions.setdefault(str(entry.resource_id), []).append(entry.calendar_date)
    configured_days = set(project.working_days)
    weekdays = {day - 1 for day in configured_days} if configured_days <= {1, 2, 3, 4, 5} else configured_days
    return BusinessCalendar(holidays, set(range(7)) - weekdays, exceptions)


def project_elements(session: Session, project_id: uuid.UUID) -> list[GanttElement]:
    return list(
        session.scalars(
            sa.select(GanttElement)
            .where(GanttElement.project_id == project_id)
            .order_by(GanttElement.external_id)
        ).all()
    )


def project_resources(session: Session, project_id: uuid.UUID) -> list[DbResource]:
    return list(
        session.scalars(
            sa.select(DbResource).where(DbResource.project_id == project_id).order_by(DbResource.external_id)
        ).all()
    )


def _domain_tasks(session: Session, project: Project) -> tuple[list[Task], list[Resource], list[Assignment]]:
    elements = project_elements(session, project.id)
    resources = project_resources(session, project.id)
    dependencies = session.scalars(
        sa.select(DbDependency).join(GanttElement, DbDependency.successor_id == GanttElement.id).where(
            GanttElement.project_id == project.id
        )
    ).all()
    dependency_map: dict[uuid.UUID, list[Dependency]] = {}
    external_by_id = {element.id: element.external_id for element in elements}
    for dependency in dependencies:
        dependency_map.setdefault(dependency.successor_id, []).append(
            Dependency(external_by_id[dependency.predecessor_id], dependency.dependency_type.value, dependency.lag_days)
        )
    db_assignments = session.scalars(
        sa.select(DbAssignment).join(GanttElement, DbAssignment.element_id == GanttElement.id).where(
            GanttElement.project_id == project.id
        )
    ).all()
    assignments_by_element: dict[uuid.UUID, list[Assignment]] = {}
    for assignment in db_assignments:
        assignments_by_element.setdefault(assignment.element_id, []).append(
            Assignment(
                external_by_id[assignment.element_id],
                str(assignment.resource_id),
                assignment.planned_hours,
                assignment.quantity,
                assignment.hours_per_day,
                assignment.rate_override,
            )
        )
    domain_resources = [
        Resource(
            str(resource.id),
            resource.name,
            resource.resource_type.value,
            resource.rate,
            resource.rate,
            resource.capacity_hours_per_day or Decimal("0"),
        )
        for resource in resources
    ]
    domain_tasks = [
        Task(
            element.external_id,
            element.name,
            element.element_type.value,
            next((parent.external_id for parent in elements if parent.id == element.parent_id), None),
            element.planned_start,
            element.planned_finish,
            element.duration_days,
            tuple(dependency_map.get(element.id, [])),
            element.effort_hours,
            element.progress_pct,
            element.actual_start,
            element.actual_finish,
            element.actual_cost,
            element.planned_cost,
            element.total_slack_days,
            element.free_slack_days,
            element.is_critical,
            tuple(assignments_by_element.get(element.id, [])),
        )
        for element in elements
    ]
    return domain_tasks, domain_resources, [item for values in assignments_by_element.values() for item in values]


def recalculate_project(session: Session, project: Project) -> dict[str, Any]:
    tasks, resources, assignments = _domain_tasks(session, project)
    schedulable = [task for task in tasks if task.kind in {"SUBACTIVIDAD", "HITO"}]
    if not schedulable:
        raise ApiError("EMPTY_SCHEDULE", "El proyecto no tiene elementos planificables")
    calendar = project_calendar(session, project)
    engine = DeterministicCalculationEngine(calendar)
    result = engine.schedule(schedulable, project.planned_start, project.committed_finish)
    by_external = {element.external_id: element for element in project_elements(session, project.id)}
    for task in result.tasks.values():
        element = by_external[task.task_id]
        element.planned_start = task.start
        element.planned_finish = task.finish
        element.duration_days = task.duration_days
        element.total_slack_days = task.total_slack_days
        element.free_slack_days = task.free_slack_days
        element.is_critical = task.critical
    costs = engine.calculate_costs(tasks, resources, assignments)
    for task_id, value in costs.consolidated.items():
        if task_id in by_external:
            by_external[task_id].planned_cost = value.planned_cost
            by_external[task_id].actual_cost = value.actual_cost
            by_external[task_id].progress_pct = value.progress_pct
            by_external[task_id].planned_start = value.start
            by_external[task_id].planned_finish = value.finish
    session.flush()
    return {
        "project_start": result.project_start,
        "project_finish": result.project_finish,
        "changed_elements": [change.task_id for change in result.changes],
        "planned_cost": costs.project.planned_cost,
        "actual_cost": costs.project.actual_cost,
    }


class SqlAlchemyImportStore:
    """Transactional adapter from the canonical importer to the F1 schema."""

    def __init__(self, session: Session, project_id: uuid.UUID | None = None) -> None:
        self.session = session
        self.project_id = project_id
        self.baseline_version: str | None = None

    def commit_import(self, workbook: CanonicalWorkbook) -> int:
        values = {str(row.get("clave", "")): str(row.get("valor", "")).strip() for row in workbook.sheets["Proyecto"]}
        code = values.get("codigo", "").strip()
        if not code:
            raise ApiError("INVALID_IMPORT", "La importación no contiene código de proyecto")
        project = self.session.get(Project, self.project_id) if self.project_id else None
        if project is None:
            project = self.session.scalar(sa.select(Project).where(Project.code == code))
        if project is None:
            project = Project(code=code, name=values.get("nombre", code))
            self.session.add(project)
            self.session.flush()
        self._replace_plan(project)
        self._update_project(project, values)
        self._write_resources(project, workbook)
        external_elements = self._write_elements(project, workbook)
        self._write_calendar(project, workbook)
        self._write_assignments(project, workbook, external_elements)
        self._write_milestones(workbook, external_elements)
        self._write_baseline(project, workbook, external_elements)
        self._write_supplemental(project, workbook)
        project.status = ProjectStatus.ACTIVE
        self.session.flush()
        return sum(len(rows) for rows in workbook.sheets.values())

    def _write_supplemental(self, project: Project, workbook: CanonicalWorkbook) -> None:
        """Persist optional Seed B change, KPI and dashboard definitions."""

        stages_by_sequence: dict[int, ChangeStage] = {}
        for row in workbook.sheets.get("Etapas_Cambio", []):
            sequence = int(row.get("secuencia", 0))
            if sequence <= 0:
                continue
            stage = self.session.scalar(
                sa.select(ChangeStage).where(
                    ChangeStage.project_id == project.id,
                    ChangeStage.sequence == sequence,
                )
            )
            if stage is None:
                stage = ChangeStage(project_id=project.id, sequence=sequence)
                self.session.add(stage)
            stage.name = str(row.get("nombre", "")).strip()
            stage.sla_hours = _integer(row.get("sla_horas"))
            stage.is_active = True
            stages_by_sequence[sequence] = stage
        self.session.flush()
        for row in workbook.sheets.get("Cambios", []):
            code = str(row.get("id", "")).strip()
            if not code:
                continue
            change = self.session.scalar(
                sa.select(ChangeRequest).where(
                    ChangeRequest.project_id == project.id,
                    ChangeRequest.code == code,
                )
            )
            stage_name = str(row.get("etapa_actual", "")).strip()
            stage = next((item for item in stages_by_sequence.values() if item.name == stage_name), None)
            if change is None:
                change = ChangeRequest(project_id=project.id, code=code, title=str(row.get("titulo", code)))
                self.session.add(change)
            change.title = str(row.get("titulo", code))
            change.description = change.title
            change.change_type = ChangeType(str(row.get("tipo", "ALCANCE")))
            change.priority = ChangePriority(str(row.get("prioridad", "MEDIA")))
            change.status = ChangeStatus(str(row.get("estado", "ABIERTA")))
            change.current_stage_id = stage.id if stage is not None else None
            if stage is not None:
                stage_sequence = stage.sequence
                for workflow_stage in stages_by_sequence.values():
                    record = self.session.scalar(
                        sa.select(ChangeRequestStage).where(
                            ChangeRequestStage.request_id == change.id,
                            ChangeRequestStage.stage_id == workflow_stage.id,
                        )
                    )
                    if record is None:
                        record = ChangeRequestStage(
                            request_id=change.id,
                            stage_id=workflow_stage.id,
                        )
                        self.session.add(record)
                    record.status = (
                        ChangeStageStatus.COMPLETED
                        if workflow_stage.sequence < stage_sequence
                        else ChangeStageStatus.ACTIVE
                        if workflow_stage.sequence == stage_sequence
                        else ChangeStageStatus.PENDING
                    )
        for row in workbook.sheets.get("KPI_Proyecto_Hitos", []) + workbook.sheets.get("KPI_Cambio", []):
            code = str(row.get("codigo", "")).strip()
            if not code:
                continue
            kpi = self.session.scalar(
                sa.select(Kpi).where(Kpi.project_id == project.id, Kpi.code == code)
            )
            if kpi is None:
                kpi = Kpi(project_id=project.id, code=code, name=code, formula="0", scope=KpiScope.PROJECT)
                self.session.add(kpi)
            kpi.name = str(row.get("nombre", code))
            kpi.formula = str(row.get("formula", "0"))
            kpi.scope = KpiScope(str(row.get("ambito", "PROYECTO")))
            kpi.target = _optional_decimal(row.get("meta"))
            kpi.is_active = True
        for row in workbook.sheets.get("Tableros", []):
            external_id = str(row.get("id", "")).strip()
            if not external_id:
                continue
            dashboard = self.session.scalar(
                sa.select(Dashboard).where(
                    Dashboard.project_id == project.id,
                    Dashboard.external_id == external_id,
                )
            )
            if dashboard is None:
                dashboard = Dashboard(project_id=project.id, external_id=external_id, name=external_id, dashboard_type="PROYECTO")
                self.session.add(dashboard)
            dashboard.name = str(row.get("nombre", external_id))
            dashboard.dashboard_type = str(row.get("tipo", "PROYECTO"))
            raw_kpis = row.get("kpis", [])
            if isinstance(raw_kpis, list):
                dashboard.kpi_codes = [str(item) for item in raw_kpis]
            else:
                text = str(raw_kpis).strip()
                try:
                    parsed = json.loads(text.replace("'", '"')) if text.startswith("[") else None
                except json.JSONDecodeError:
                    parsed = None
                dashboard.kpi_codes = parsed if isinstance(parsed, list) else [item.strip() for item in text.split(",") if item.strip()]
        self.session.flush()

    def _replace_plan(self, project: Project) -> None:
        element_ids = list(
            self.session.scalars(sa.select(GanttElement.id).where(GanttElement.project_id == project.id)).all()
        )
        if element_ids:
            self.session.query(BaselineElement).filter(
                BaselineElement.project_id == project.id,
                BaselineElement.element_id.in_(element_ids),
            ).update({BaselineElement.element_id: None}, synchronize_session=False)
            self.session.query(DbAssignment).filter(DbAssignment.element_id.in_(element_ids)).delete(
                synchronize_session=False
            )
            self.session.query(DbDependency).filter(
                sa.or_(DbDependency.predecessor_id.in_(element_ids), DbDependency.successor_id.in_(element_ids))
            ).delete(synchronize_session=False)
            self.session.query(ProgressRecord).filter(ProgressRecord.element_id.in_(element_ids)).delete(
                synchronize_session=False
            )
            self.session.query(ActualCost).filter(ActualCost.element_id.in_(element_ids)).delete(
                synchronize_session=False
            )
            self.session.query(MilestoneTask).filter(
                sa.or_(MilestoneTask.milestone_id.in_(element_ids), MilestoneTask.element_id.in_(element_ids))
            ).delete(synchronize_session=False)
            self.session.query(Milestone).filter(Milestone.element_id.in_(element_ids)).delete(
                synchronize_session=False
            )
            elements = list(self.session.scalars(sa.select(GanttElement).where(GanttElement.id.in_(element_ids))).all())
            for element in sorted(elements, key=lambda item: _element_depth(item, elements), reverse=True):
                self.session.delete(element)
        self.session.query(CalendarEntry).filter(CalendarEntry.project_id == project.id).delete(
            synchronize_session=False
        )
        self.session.query(DbResource).filter(DbResource.project_id == project.id).delete(
            synchronize_session=False
        )
        self.session.flush()

    def _update_project(self, project: Project, values: dict[str, str]) -> None:
        project.name = values.get("nombre", project.name)
        project.client = values.get("cliente") or None
        project.planned_start = _parse_optional_date(values.get("fecha_inicio"))
        project.committed_finish = _parse_optional_date(values.get("fecha_comprometida"))
        project.cutoff_date = _parse_optional_date(values.get("fecha_corte"))
        project.budget = _decimal(values.get("presupuesto"))
        project.contingency_pct = _decimal(values.get("contingencia_pct"))
        project.working_hours_per_day = _decimal(values.get("horas_por_dia"), Decimal("8"))
        project.working_days = [1, 2, 3, 4, 5]

    def _write_resources(self, project: Project, workbook: CanonicalWorkbook) -> None:
        for row in workbook.sheets["Recursos"]:
            self.session.add(
                DbResource(
                    project_id=project.id,
                    external_id=str(row.get("recurso_id", "")),
                    name=str(row.get("nombre", "")),
                    resource_type=ResourceType(str(row.get("tipo", "HUMANO"))),
                    role=str(row.get("rol", "")) or None,
                    rate=_decimal(row.get("tarifa")),
                    unit=str(row.get("unidad", "")) or None,
                    capacity_hours_per_day=_decimal(row.get("capacidad_h_dia"), Decimal("0")),
                )
            )
        self.session.flush()

    def _write_elements(self, project: Project, workbook: CanonicalWorkbook) -> dict[str, GanttElement]:
        rows = workbook.sheets["Gantt"]
        elements: dict[str, GanttElement] = {}
        pending = list(rows)
        while pending:
            progress = False
            for row in pending[:]:
                parent_external = str(row.get("padre_id", "")).strip()
                if parent_external and parent_external not in elements:
                    continue
                element = GanttElement(
                    project_id=project.id,
                    external_id=str(row.get("id", "")),
                    element_type=GanttElementType(str(row.get("tipo", "SUBACTIVIDAD"))),
                    name=str(row.get("nombre", "")),
                    parent_id=elements[parent_external].id if parent_external else None,
                    planned_start=row.get("inicio_plan"),
                    planned_finish=row.get("fin_plan"),
                    duration_days=_integer(row.get("duracion_dias")),
                    progress_pct=_decimal(row.get("avance_pct")),
                    actual_start=row.get("inicio_real"),
                    actual_finish=row.get("fin_real"),
                    actual_cost=_decimal(row.get("costo_real")),
                )
                self.session.add(element)
                self.session.flush()
                elements[element.external_id] = element
                pending.remove(row)
                progress = True
            if not progress:
                raise ApiError("INVALID_IMPORT", "La jerarquía de Gantt contiene padres no resolubles")
        for row in rows:
            successor = elements[str(row.get("id", ""))]
            for predecessor in parse_predecessors(str(row.get("predecesoras", ""))):
                if predecessor.predecessor_id not in elements:
                    raise ApiError("INVALID_IMPORT", f"Predecesora inexistente: {predecessor.predecessor_id}")
                self.session.add(
                DbDependency(
                        project_id=project.id,
                        predecessor_id=elements[predecessor.predecessor_id].id,
                        successor_id=successor.id,
                        dependency_type=predecessor.dependency_type,
                        lag_days=predecessor.lag_days,
                    )
                )
        self.session.flush()
        return elements

    def _write_calendar(self, project: Project, workbook: CanonicalWorkbook) -> None:
        resources = {
            resource.external_id: resource.id
            for resource in self.session.scalars(
                sa.select(DbResource).where(DbResource.project_id == project.id)
            ).all()
        }
        for row in workbook.sheets["Calendario"]:
            resource_id = resources.get(str(row.get("recurso_id", "")).strip())
            self.session.add(
                CalendarEntry(
                    project_id=project.id,
                    calendar_date=row["fecha"],
                    day_type=CalendarDayType(str(row.get("tipo", "FERIADO"))),
                    resource_id=resource_id,
                    description=str(row.get("descripcion", "")) or None,
                )
            )

    def _write_assignments(
        self, project: Project, workbook: CanonicalWorkbook, elements: dict[str, GanttElement]
    ) -> None:
        resources = {
            resource.external_id: resource.id
            for resource in self.session.scalars(
                sa.select(DbResource).where(DbResource.project_id == project.id)
            ).all()
        }
        for row in workbook.sheets["Asignaciones"]:
            self.session.add(
                DbAssignment(
                    project_id=project.id,
                    element_id=elements[str(row.get("tarea_id", ""))].id,
                    resource_id=resources[str(row.get("recurso_id", ""))],
                    planned_hours=_decimal(row.get("horas_planificadas")),
                    quantity=_decimal(row.get("cantidad")),
                    hours_per_day=_decimal(row.get("h_dia")),
                    rate_override=_optional_decimal(row.get("tarifa_override")),
                )
            )

    def _write_milestones(self, workbook: CanonicalWorkbook, elements: dict[str, GanttElement]) -> None:
        for row in workbook.sheets["Gantt"]:
            if str(row.get("tipo", "")).upper() == "HITO":
                milestone_id = elements[str(row["id"])].id
                self.session.add(Milestone(element_id=milestone_id))
        self.session.flush()
        for row in workbook.sheets["Criterios"]:
            milestone = elements.get(str(row.get("hito_id", "")))
            if milestone is not None:
                self.session.add(
                    AcceptanceCriterion(
                        milestone_id=milestone.id,
                        external_id=str(row.get("criterio_id", "")),
                        description=str(row.get("descripcion", "")),
                        verification_method=str(row.get("forma_de_verificacion", "")),
                    )
                )
        for row in workbook.sheets["Hitos_Tareas"]:
            milestone = elements.get(str(row.get("hito_id", "")))
            task = elements.get(str(row.get("tarea_id", "")))
            if milestone is not None and task is not None:
                self.session.add(MilestoneTask(milestone_id=milestone.id, element_id=task.id))

    def _write_baseline(self, project: Project, workbook: CanonicalWorkbook, elements: dict[str, GanttElement]) -> None:
        active = self.session.scalar(
            sa.select(Baseline).where(
                Baseline.project_id == project.id,
                Baseline.status == BaselineStatus.ACTIVE,
            )
        )
        if active is not None:
            active.status = BaselineStatus.SUPERSEDED
            self.session.flush()
        versions = self.session.scalars(
            sa.select(Baseline.version).where(Baseline.project_id == project.id)
        ).all()
        next_version = max((_baseline_number(version) for version in versions), default=0) + 1
        baseline = Baseline(project_id=project.id, version=f"v{next_version}")
        self.session.add(baseline)
        self.session.flush()
        tasks, resources, assignments = _domain_tasks(self.session, project)
        costs = CostCalculator().calculate(tasks, resources, assignments)
        for row in workbook.sheets["Gantt"]:
            self.session.add(
                BaselineElement(
                    baseline_id=baseline.id,
                    project_id=project.id,
                    element_id=elements[str(row["id"])].id,
                    external_id=str(row["id"]),
                    parent_external_id=str(row.get("padre_id", "")) or None,
                    element_type=GanttElementType(str(row["tipo"])),
                    name=str(row["nombre"]),
                    planned_start=row.get("inicio_plan"),
                    planned_finish=row.get("fin_plan"),
                    duration_days=_integer(row.get("duracion_dias")),
                    planned_cost=costs.consolidated[str(row["id"])].planned_cost,
                )
            )
        self.session.flush()
        # The snapshot is sealed only after every immutable child row exists.
        baseline.approved_at = utc_now()
        self.baseline_version = baseline.version


def _baseline_number(version: str) -> int:
    normalized = version.strip().lower()
    if normalized.startswith("v"):
        normalized = normalized[1:]
    major = normalized.split(".", 1)[0]
    return int(major)


def import_workbook(session: Session, source: Path, project_id: uuid.UUID | None = None) -> ImportResult:
    store = SqlAlchemyImportStore(session, project_id)
    result = ImportService(store).import_file(source)
    if not result.imported:
        return result
    return result


def _parse_optional_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if value in (None, ""):
        return default
    return Decimal(str(value).replace(",", ".").replace("%", "").strip())


def _optional_decimal(value: Any) -> Decimal | None:
    return None if value in (None, "") else _decimal(value)


def _integer(value: Any) -> int | None:
    return None if value in (None, "") else int(float(str(value).replace(",", ".")))


def _element_depth(element: GanttElement, elements: list[GanttElement]) -> int:
    by_id = {item.id: item for item in elements}
    depth = 0
    parent_id = element.parent_id
    while parent_id is not None and parent_id in by_id:
        depth += 1
        parent_id = by_id[parent_id].parent_id
    return depth
