"""REST resources for the first complete Trazo vertical slice."""

# FastAPI's dependency declaration is intentionally expressed in the function
# signature; B008 would otherwise flag the framework's standard pattern.
# ruff: noqa: B008

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.api.schemas import (
    AssignmentCreate,
    ChangeCreate,
    ChangeTransitionCreate,
    GanttCreate,
    GanttUpdate,
    ImportRequest,
    KpiCreate,
    KpiUpdate,
    KpiVariableCreate,
    ProgressCreate,
    ProjectCreate,
    ProjectUpdate,
    ResourceCreate,
)
from app.audit import record_audit
from app.auth import MANAGEMENT_ROLES, get_current_user, require_roles
from app.db import get_db
from app.models import (
    Assignment,
    AcceptanceCriterion,
    ChangeRequest,
    ChangeRequestStage,
    ChangeImpact,
    ChangeStage,
    ChangeStageStatus,
    ChangeStatus,
    Dashboard,
    GanttElement,
    Kpi,
    KpiFormulaVersion,
    KpiVariable,
    KpiValue,
    Evidence,
    Project,
    ProjectStatus,
    ProgressRecord,
    Resource,
    User,
    utc_now,
)
from app.services.persistence import (
    import_workbook,
    project_calendar,
    project_elements,
    project_resources,
    recalculate_project,
    require_project,
)
from app.services.f7 import ChangeControlService, DEFAULT_CHANGE_STAGES, F7Error
from app.domain.models import Assignment as DomainAssignment
from app.domain.models import Resource as DomainResource
from app.domain.models import Task
from app.services.calculation_engine import DeterministicCalculationEngine
from app.services.scheduler import ScheduleError, parse_predecessors
from app.services.kpi import (
    DEFAULT_KPI_VARIABLES,
    KpiFormulaError,
    evaluate_formula,
    formula_variables,
    validate_formula,
)

router = APIRouter(prefix="/api/v1", tags=["projects"])
CurrentUser = Annotated[User, Depends(get_current_user)]
Manager = Annotated[User, Depends(require_roles(*MANAGEMENT_ROLES))]


def _ok(data: Any, **meta: Any) -> dict[str, Any]:
    response: dict[str, Any] = {"data": data}
    if meta:
        response["meta"] = meta
    return response


def _import_source(source_path: str) -> Path:
    """Resolve an import source inside the explicitly published seed directory."""

    source = Path(source_path).expanduser().resolve()
    import_root = (Path(__file__).resolve().parents[2] / "seeds").resolve()
    try:
        source.relative_to(import_root)
    except ValueError as error:
        raise ApiError("INVALID_IMPORT_SOURCE", "El origen de importación no está permitido") from error
    if "insumos" in {part.casefold() for part in source.parts} or not source.exists():
        raise ApiError("INVALID_IMPORT_SOURCE", "Los insumos académicos no se pueden importar desde la API")
    if source.is_file() and source.suffix.casefold() not in {".xlsx", ".csv"}:
        raise ApiError("INVALID_IMPORT_SOURCE", "El origen debe ser XLSX, CSV o un directorio CSV")
    if source.is_dir() and not source.name:
        raise ApiError("INVALID_IMPORT_SOURCE", "El origen de importación no es válido")
    return source


def _project(project: Project) -> dict[str, Any]:
    return {
        "id": project.id,
        "code": project.code,
        "name": project.name,
        "client": project.client,
        "status": project.status.value,
        "planned_start": project.planned_start,
        "committed_finish": project.committed_finish,
        "cutoff_date": project.cutoff_date,
        "budget": project.budget,
        "contingency_pct": project.contingency_pct,
        "working_hours_per_day": project.working_hours_per_day,
        "working_days": project.working_days,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
    }


def _validate_project_closure(session: Session, project: Project) -> None:
    """Require operational completion, closed changes and a closure record."""

    unfinished = session.scalar(
        sa.select(sa.func.count(GanttElement.id)).where(
            GanttElement.project_id == project.id,
            GanttElement.element_type == "SUBACTIVIDAD",
            GanttElement.progress_pct < 100,
        )
    ) or 0
    if unfinished:
        raise ApiError(
            "PROJECT_NOT_READY",
            "No se puede cerrar: existen subactividades con avance menor a 100 %",
            409,
            {"unfinished_subactivities": int(unfinished)},
        )
    open_changes = session.scalar(
        sa.select(sa.func.count(ChangeRequest.id)).where(
            ChangeRequest.project_id == project.id,
            ChangeRequest.status != ChangeStatus.CLOSED,
        )
    ) or 0
    if open_changes:
        raise ApiError(
            "PROJECT_NOT_READY",
            "No se puede cerrar: existen solicitudes de cambio sin cerrar",
            409,
            {"open_changes": int(open_changes)},
        )
    closure_evidence = session.scalar(
        sa.select(sa.func.count(Evidence.id))
        .outerjoin(AcceptanceCriterion, Evidence.criterion_id == AcceptanceCriterion.id)
        .outerjoin(GanttElement, AcceptanceCriterion.milestone_id == GanttElement.id)
        .outerjoin(ChangeRequest, Evidence.change_request_id == ChangeRequest.id)
        .where(
            sa.or_(
                GanttElement.project_id == project.id,
                ChangeRequest.project_id == project.id,
            ),
            sa.or_(
                sa.func.lower(Evidence.file_name).like("%acta%"),
                sa.func.lower(Evidence.storage_key).like("%acta%"),
            ),
        )
    ) or 0
    if not closure_evidence:
        raise ApiError(
            "PROJECT_NOT_READY",
            "No se puede cerrar: falta adjuntar el acta de cierre",
            409,
        )


def _element(session: Session, element: GanttElement) -> dict[str, Any]:
    parent = session.get(GanttElement, element.parent_id) if element.parent_id else None
    return {
        "id": element.id,
        "external_id": element.external_id,
        "element_type": element.element_type.value,
        "name": element.name,
        "parent_id": element.parent_id,
        "parent_external_id": parent.external_id if parent else None,
        "planned_start": element.planned_start,
        "planned_finish": element.planned_finish,
        "duration_days": element.duration_days,
        "actual_start": element.actual_start,
        "actual_finish": element.actual_finish,
        "progress_pct": element.progress_pct,
        "planned_cost": element.planned_cost,
        "actual_cost": element.actual_cost,
        "effort_hours": element.effort_hours,
        "total_slack_days": element.total_slack_days,
        "free_slack_days": element.free_slack_days,
        "is_critical": element.is_critical,
    }


def _validate_parent_type(element_type: Any, parent: GanttElement | None) -> None:
    """Enforce the canonical ETAPA → ACTIVIDAD → SUBACTIVIDAD hierarchy."""

    kind = element_type.value if hasattr(element_type, "value") else str(element_type)
    expected = {
        "ETAPA": None,
        "ACTIVIDAD": {"ETAPA"},
        "SUBACTIVIDAD": {"ACTIVIDAD"},
        "HITO": {"ACTIVIDAD", "ETAPA"},
    }
    if kind not in expected:
        raise ApiError("INVALID_HIERARCHY", f"Tipo Gantt inválido: {kind}")
    if parent is None and expected[kind] is not None:
        raise ApiError("INVALID_HIERARCHY", f"{kind} requiere un padre válido")
    if parent is not None and expected[kind] is None:
        raise ApiError("INVALID_HIERARCHY", "Una ETAPA no puede tener padre")
    if parent is not None and parent.element_type.value not in expected[kind]:
        raise ApiError("INVALID_HIERARCHY", f"{kind} no puede depender de {parent.element_type.value}")


def _validate_project_graph(session: Session, project: Project) -> None:
    """Run the shared cycle/reference validator before exposing a plan."""

    tasks, _, _ = _calculation_inputs(session, project)
    try:
        DeterministicCalculationEngine(project_calendar(session, project)).scheduler.validate_graph(tasks)
    except ScheduleError as exc:
        raise ApiError("INVALID_DEPENDENCY", str(exc)) from exc


def _recalculate_gantt(session: Session, project: Project) -> None:
    if any(element.element_type.value in {"SUBACTIVIDAD", "HITO"} for element in project_elements(session, project.id)):
        try:
            recalculate_project(session, project)
        except ValueError as exc:
            raise ApiError("INVALID_SCHEDULE", str(exc)) from exc


@router.get("/projects", tags=["projects"])
def list_projects(session: Session = Depends(get_db), _: CurrentUser = None) -> dict[str, Any]:
    projects = session.scalars(sa.select(Project).order_by(Project.code)).all()
    return _ok([_project(project) for project in projects], total=len(projects))


@router.post("/projects", status_code=201, tags=["projects"])
def create_project(payload: ProjectCreate, session: Session = Depends(get_db), _: Manager = None) -> dict[str, Any]:
    if payload.status == ProjectStatus.CLOSED:
        raise ApiError("PROJECT_NOT_READY", "Un proyecto nuevo no puede crearse cerrado", 409)
    project = Project(**payload.model_dump())
    session.add(project)
    session.commit()
    session.refresh(project)
    return _ok(_project(project))


@router.get("/projects/{project_id}", tags=["projects"])
def get_project(project_id: uuid.UUID, session: Session = Depends(get_db), _: CurrentUser = None) -> dict[str, Any]:
    return _ok(_project(require_project(session, project_id)))


@router.patch("/projects/{project_id}", tags=["projects"])
def update_project(project_id: uuid.UUID, payload: ProjectUpdate, session: Session = Depends(get_db), _: Manager = None) -> dict[str, Any]:
    project = require_project(session, project_id)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("status") == ProjectStatus.CLOSED:
        _validate_project_closure(session, project)
    for key, value in changes.items():
        setattr(project, key, value)
    session.commit()
    session.refresh(project)
    return _ok(_project(project))


@router.post("/projects/import/preview", tags=["imports"])
def preview_import(payload: ImportRequest, _: CurrentUser) -> dict[str, Any]:
    from trazo_importer.service import ImportService

    try:
        result = ImportService().preview(_import_source(payload.source_path))
    except (FileNotFoundError, ValueError) as exc:
        raise ApiError("INVALID_IMPORT_SOURCE", str(exc)) from exc
    return _ok(
        {
            "valid": result.report.valid,
            "report": result.report.as_dict(),
            "project_code": result.preview.project_code,
            "baseline_version": result.baseline_version,
            "sheets": {name: len(rows) for name, rows in result.preview.sheets.items()},
        }
    )


@router.post("/projects/import", status_code=201, tags=["imports"])
def import_project(payload: ImportRequest, session: Session = Depends(get_db), _: Manager = None) -> dict[str, Any]:
    try:
        result = import_workbook(session, _import_source(payload.source_path))
    except (FileNotFoundError, ValueError, KeyError) as exc:
        session.rollback()
        raise ApiError("INVALID_IMPORT", str(exc)) from exc
    if not result.report.valid:
        session.rollback()
        raise ApiError("INVALID_IMPORT", "La importación contiene errores", details=result.report.as_dict())
    session.commit()
    project = session.scalar(sa.select(Project).where(Project.code == result.preview.project_code))
    if project is None:
        raise ApiError("IMPORT_FAILED", "No fue posible crear el proyecto", 500)
    return _ok(
        {
            "project": _project(project),
            "imported": result.imported,
            "changed_rows": result.changed_rows,
            "baseline_version": result.baseline_version,
            "report": result.report.as_dict(),
        }
    )


@router.post("/projects/{project_id}/imports", tags=["imports"])
def import_project_version(
    project_id: uuid.UUID, payload: ImportRequest, session: Session = Depends(get_db), _: Manager = None
) -> dict[str, Any]:
    require_project(session, project_id)
    try:
        result = import_workbook(session, _import_source(payload.source_path), project_id)
    except (FileNotFoundError, ValueError, KeyError) as exc:
        session.rollback()
        raise ApiError("INVALID_IMPORT", str(exc)) from exc
    if not result.report.valid:
        session.rollback()
        raise ApiError("INVALID_IMPORT", "La importación contiene errores", details=result.report.as_dict())
    session.commit()
    return _ok(
        {
            "imported": True,
            "changed_rows": result.changed_rows,
            "baseline_version": result.baseline_version,
            "report": result.report.as_dict(),
        }
    )


@router.get("/projects/{project_id}/gantt", tags=["gantt"])
def list_gantt(project_id: uuid.UUID, session: Session = Depends(get_db), _: CurrentUser = None) -> dict[str, Any]:
    require_project(session, project_id)
    elements = project_elements(session, project_id)
    return _ok([_element(session, element) for element in elements], total=len(elements))


@router.post("/projects/{project_id}/gantt", status_code=201, tags=["gantt"])
def create_gantt_element(
    project_id: uuid.UUID, payload: GanttCreate, session: Session = Depends(get_db), _: Manager = None
) -> dict[str, Any]:
    project = require_project(session, project_id)
    duplicate = session.scalar(
        sa.select(GanttElement).where(
            GanttElement.project_id == project_id,
            GanttElement.external_id == payload.external_id,
        )
    )
    if duplicate is not None:
        raise ApiError("CONFLICT", "El identificador Gantt ya existe", 409)
    parent = None
    if payload.parent_external_id:
        parent = session.scalar(
            sa.select(GanttElement).where(
                GanttElement.project_id == project_id,
                GanttElement.external_id == payload.parent_external_id,
            )
        )
        if parent is None:
            raise ApiError("NOT_FOUND", "Padre Gantt no encontrado", 404)
    _validate_parent_type(payload.element_type, parent)
    if payload.element_type.value in {"ETAPA", "ACTIVIDAD"} and any(
        value is not None
        for value in (payload.planned_start, payload.planned_finish, payload.duration_days)
    ):
        raise ApiError("INVALID_HIERARCHY", "ETAPA y ACTIVIDAD consolidan fechas y duración")
    element = GanttElement(
        project_id=project_id,
        external_id=payload.external_id,
        element_type=payload.element_type,
        name=payload.name,
        parent_id=parent.id if parent else None,
        planned_start=payload.planned_start,
        planned_finish=payload.planned_finish,
        duration_days=payload.duration_days,
        progress_pct=payload.progress_pct,
        planned_cost=payload.planned_cost,
        effort_hours=payload.effort_hours,
    )
    session.add(element)
    session.flush()
    if payload.predecessors:
        from app.models import Dependency as DbDependency

        known = {
            item.external_id: item
            for item in project_elements(session, project_id)
        }
        for dependency in parse_predecessors(payload.predecessors):
            predecessor = known.get(dependency.predecessor_id)
            if predecessor is None:
                raise ApiError("INVALID_DEPENDENCY", "Predecesora Gantt no encontrada")
            if predecessor.id == element.id:
                raise ApiError("INVALID_DEPENDENCY", "Un elemento no puede depender de sí mismo")
            if predecessor.element_type.value not in {"SUBACTIVIDAD", "HITO"} or payload.element_type.value not in {
                "SUBACTIVIDAD",
                "HITO",
            }:
                raise ApiError("INVALID_DEPENDENCY", "Las dependencias solo conectan hojas e hitos")
            session.add(
                DbDependency(
                    project_id=project_id,
                    predecessor_id=predecessor.id,
                    successor_id=element.id,
                    dependency_type=dependency.dependency_type,
                    lag_days=dependency.lag_days,
                )
            )
    try:
        _validate_project_graph(session, project)
        _recalculate_gantt(session, project)
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(element)
    return _ok(_element(session, element))


@router.patch("/projects/{project_id}/gantt/{element_id}", tags=["gantt"])
def update_gantt_element(
    project_id: uuid.UUID,
    element_id: uuid.UUID,
    payload: GanttUpdate,
    session: Session = Depends(get_db),
    _: Manager = None,
) -> dict[str, Any]:
    project = require_project(session, project_id)
    element = session.scalar(
        sa.select(GanttElement).where(GanttElement.id == element_id, GanttElement.project_id == project_id)
    )
    if element is None:
        raise ApiError("NOT_FOUND", "Elemento Gantt no encontrado", 404)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(element, key, value)
    try:
        _validate_project_graph(session, project)
        _recalculate_gantt(session, project)
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(element)
    return _ok(_element(session, element))


@router.post("/projects/{project_id}/gantt/{element_id}/progress", status_code=201, tags=["gantt"])
def record_progress(
    project_id: uuid.UUID,
    element_id: uuid.UUID,
    payload: ProgressCreate,
    session: Session = Depends(get_db),
    actor: CurrentUser = None,
) -> dict[str, Any]:
    require_project(session, project_id)
    element = session.scalar(
        sa.select(GanttElement).where(GanttElement.id == element_id, GanttElement.project_id == project_id)
    )
    if element is None:
        raise ApiError("NOT_FOUND", "Elemento Gantt no encontrado", 404)
    element.progress_pct = payload.progress_pct
    element.actual_start = payload.actual_start
    element.actual_finish = payload.actual_finish
    record = ProgressRecord(element_id=element_id, recorded_by=actor.id, **payload.model_dump())
    session.add(record)
    session.commit()
    return _ok({"element_id": element_id, "progress_pct": element.progress_pct, "cutoff_at": payload.cutoff_at})


@router.post("/projects/{project_id}/recalculate", tags=["calculation"])
def recalculate(project_id: uuid.UUID, session: Session = Depends(get_db), _: Manager = None) -> dict[str, Any]:
    project = require_project(session, project_id)
    result = recalculate_project(session, project)
    session.commit()
    return _ok(result)


@router.get("/projects/{project_id}/resources", tags=["resources"])
def list_resources(project_id: uuid.UUID, session: Session = Depends(get_db), _: CurrentUser = None) -> dict[str, Any]:
    require_project(session, project_id)
    resources = project_resources(session, project_id)
    return _ok([resource.model_dump() if hasattr(resource, "model_dump") else _resource(resource) for resource in resources], total=len(resources))


def _resource(resource: Resource) -> dict[str, Any]:
    return {
        "id": resource.id,
        "external_id": resource.external_id,
        "name": resource.name,
        "resource_type": resource.resource_type.value,
        "role": resource.role,
        "rate": resource.rate,
        "unit": resource.unit,
        "capacity_hours_per_day": resource.capacity_hours_per_day,
    }


@router.post("/projects/{project_id}/resources", status_code=201, tags=["resources"])
def create_resource(
    project_id: uuid.UUID, payload: ResourceCreate, session: Session = Depends(get_db), _: Manager = None
) -> dict[str, Any]:
    require_project(session, project_id)
    resource = Resource(project_id=project_id, **payload.model_dump())
    session.add(resource)
    session.commit()
    session.refresh(resource)
    return _ok(_resource(resource))


@router.post("/projects/{project_id}/assignments", status_code=201, tags=["resources"])
def create_assignment(
    project_id: uuid.UUID, payload: AssignmentCreate, session: Session = Depends(get_db), _: Manager = None
) -> dict[str, Any]:
    require_project(session, project_id)
    element = session.scalar(sa.select(GanttElement).where(GanttElement.id == payload.element_id, GanttElement.project_id == project_id))
    resource = session.scalar(sa.select(Resource).where(Resource.id == payload.resource_id, Resource.project_id == project_id))
    if element is None or resource is None:
        raise ApiError("NOT_FOUND", "Elemento o recurso no encontrado", 404)
    assignment = Assignment(project_id=project_id, **payload.model_dump())
    session.add(assignment)
    session.commit()
    session.refresh(assignment)
    return _ok({"id": assignment.id, **payload.model_dump()})


@router.get("/projects/{project_id}/costs", tags=["costs"])
def project_costs(project_id: uuid.UUID, session: Session = Depends(get_db), _: CurrentUser = None) -> dict[str, Any]:
    project = require_project(session, project_id)
    tasks, resources, assignments = _calculation_inputs(session, project)
    report = DeterministicCalculationEngine(project_calendar(session, project)).calculate_costs(
        tasks, resources, assignments
    )
    return _ok(
        {
            "project": report.project,
            "by_task": report.by_task,
            "consolidated": report.consolidated,
        }
    )


def _calculation_inputs(session: Session, project: Project) -> tuple[list[Task], list[DomainResource], list[DomainAssignment]]:
    from app.services.persistence import _domain_tasks

    return _domain_tasks(session, project)


@router.get("/projects/{project_id}/kpis", tags=["kpis"])
def list_kpis(project_id: uuid.UUID, session: Session = Depends(get_db), _: CurrentUser = None) -> dict[str, Any]:
    require_project(session, project_id)
    kpis = session.scalars(sa.select(Kpi).where(Kpi.project_id == project_id).order_by(Kpi.code)).all()
    return _ok([_kpi(kpi) for kpi in kpis], total=len(kpis))


def _kpi(kpi: Kpi) -> dict[str, Any]:
    return {field: getattr(kpi, field) for field in ("id", "code", "name", "formula", "scope", "element_id", "target", "green_threshold", "yellow_threshold", "red_threshold", "frequency", "alert_rule", "is_active")}


def _catalog(session: Session, project_id: uuid.UUID) -> list[dict[str, Any]]:
    """Return built-in and project-specific variables without duplicate codes."""

    result = [
        {
            "code": definition.code,
            "description": definition.description,
            "source": definition.source,
            "calculation_method": definition.calculation_method,
            "data_type": definition.data_type,
        }
        for definition in DEFAULT_KPI_VARIABLES
    ]
    known = {item["code"].upper() for item in result}
    custom = session.scalars(
        sa.select(KpiVariable).where(KpiVariable.project_id == project_id).order_by(KpiVariable.code)
    ).all()
    for variable in custom:
        if variable.code.upper() not in known:
            result.append({
                "id": variable.id,
                "code": variable.code,
                "description": variable.description,
                "source": variable.source,
                "calculation_method": variable.calculation_method,
                "data_type": variable.data_type,
            })
    return result


def _variable_codes(session: Session, project_id: uuid.UUID) -> tuple[str, ...]:
    return tuple(item["code"] for item in _catalog(session, project_id))


def _validate_formula(session: Session, project_id: uuid.UUID, formula: str) -> None:
    try:
        validate_formula(formula, _variable_codes(session, project_id))
    except KpiFormulaError as error:
        raise ApiError("INVALID_KPI_FORMULA", str(error)) from error


@router.get("/projects/{project_id}/kpis/variables", tags=["kpis"])
def list_kpi_variables(project_id: uuid.UUID, session: Session = Depends(get_db), _: CurrentUser = None) -> dict[str, Any]:
    require_project(session, project_id)
    variables = _catalog(session, project_id)
    return _ok(variables, total=len(variables))


@router.post("/projects/{project_id}/kpis/variables", status_code=201, tags=["kpis"])
def create_kpi_variable(project_id: uuid.UUID, payload: KpiVariableCreate, session: Session = Depends(get_db), _: Manager = None) -> dict[str, Any]:
    require_project(session, project_id)
    if payload.code.upper() in {item["code"].upper() for item in _catalog(session, project_id)}:
        raise ApiError("CONFLICT", "El código de variable KPI ya existe", 409)
    variable = KpiVariable(project_id=project_id, **payload.model_dump())
    session.add(variable)
    session.commit()
    session.refresh(variable)
    return _ok({
        "id": variable.id,
        "code": variable.code,
        "description": variable.description,
        "source": variable.source,
        "calculation_method": variable.calculation_method,
        "data_type": variable.data_type,
    })


@router.post("/projects/{project_id}/kpis", status_code=201, tags=["kpis"])
def create_kpi(project_id: uuid.UUID, payload: KpiCreate, session: Session = Depends(get_db), _: Manager = None) -> dict[str, Any]:
    require_project(session, project_id)
    _validate_formula(session, project_id, payload.formula)
    _validate_kpi_scope(session, project_id, payload.scope, payload.element_id)
    kpi = Kpi(project_id=project_id, **payload.model_dump())
    session.add(kpi)
    session.flush()
    session.add(KpiFormulaVersion(kpi_id=kpi.id, version=1, formula=kpi.formula))
    session.commit()
    session.refresh(kpi)
    return _ok(_kpi(kpi))


def _validate_kpi_scope(session: Session, project_id: uuid.UUID, scope: Any, element_id: uuid.UUID | None) -> None:
    scope_value = scope.value if hasattr(scope, "value") else str(scope)
    if scope_value == "PROYECTO" and element_id is not None:
        raise ApiError("INVALID_KPI_SCOPE", "Un KPI de proyecto no puede tener elemento")
    if scope_value != "PROYECTO" and element_id is None:
        raise ApiError("INVALID_KPI_SCOPE", "Un KPI de etapa o hito requiere elemento")
    if element_id is None:
        return
    element = session.scalar(sa.select(GanttElement).where(GanttElement.id == element_id, GanttElement.project_id == project_id))
    if element is None:
        raise ApiError("NOT_FOUND", "Elemento KPI no encontrado", 404)
    expected = "ETAPA" if scope_value == "ETAPA" else "HITO"
    if element.element_type.value != expected:
        raise ApiError("INVALID_KPI_SCOPE", f"El elemento debe ser de tipo {expected}")


def _project_kpi_metrics(session: Session, project_id: uuid.UUID, cutoff: date) -> dict[str, Any]:
    """Calculate the catalogue's project and change-management variables."""

    elements = session.scalars(sa.select(GanttElement).where(GanttElement.project_id == project_id)).all()
    activities = [element for element in elements if element.element_type.value == "ACTIVIDAD"]
    late = [element for element in activities if element.planned_finish and element.planned_finish < cutoff and element.progress_pct < 100]
    milestones = [element for element in elements if element.element_type.value == "HITO"]
    completed_milestones = [element for element in milestones if element.progress_pct >= 100]
    on_time_milestones = [element for element in completed_milestones if element.actual_finish is None or element.planned_finish is None or element.actual_finish <= element.planned_finish]
    planned_progress = _planned_progress(elements, cutoff)
    actual_progress = _ratio(
        sum((element.progress_pct for element in elements if element.element_type.value == "SUBACTIVIDAD"), Decimal("0")),
        len([element for element in elements if element.element_type.value == "SUBACTIVIDAD"]),
    )
    closing = next((element for element in milestones if "cierre" in element.name.casefold()), None)
    changes = session.scalars(sa.select(ChangeRequest).where(ChangeRequest.project_id == project_id)).all()
    decided = [change for change in changes if change.status in {ChangeStatus.APPROVED, ChangeStatus.REJECTED, ChangeStatus.CLOSED}]
    approved = [change for change in decided if change.status in {ChangeStatus.APPROVED, ChangeStatus.CLOSED}]
    rejected = [change for change in decided if change.status == ChangeStatus.REJECTED]
    cycle_hours = [
        Decimal(str((change.closed_at - change.created_at).total_seconds())) / Decimal("3600")
        for change in changes
        if change.closed_at is not None
    ]
    impacts = session.scalars(
        sa.select(ChangeImpact).join(ChangeRequest, ChangeImpact.request_id == ChangeRequest.id).where(ChangeRequest.project_id == project_id)
    ).all()
    evidence_changes = session.scalars(
        sa.select(sa.distinct(Evidence.change_request_id)).join(ChangeRequest, Evidence.change_request_id == ChangeRequest.id).where(ChangeRequest.project_id == project_id, Evidence.change_request_id.is_not(None))
    ).all()
    rates = {
        "CHANGE_APPROVAL_RATE": _ratio(len(approved), len(decided)),
        "CHANGE_REJECTION_RATE": _ratio(len(rejected), len(decided)),
        "CHANGE_EVIDENCE_COMPLETE_PCT": _ratio(len(evidence_changes), len(changes)),
    }
    metrics: dict[str, Any] = {
        "PHYSICAL_PROGRESS_DEVIATION": (actual_progress - planned_progress) * Decimal("100"),
        "AVANCE_REAL": actual_progress * Decimal("100"),
        "AVANCE_PLAN": planned_progress * Decimal("100"),
        "ACTIVIDADES_ATRASADAS": [1] * len(late),
        "ACTIVIDADES": [1] * len(activities),
        "HITOS_A_TIEMPO": [1] * len(on_time_milestones),
        "HITOS": [1] * len(milestones),
        "FECHA_CIERRE_REAL": (closing.actual_finish or closing.planned_finish or cutoff).toordinal() if closing else cutoff.toordinal(),
        "FECHA_CIERRE_BASE": (closing.planned_finish or cutoff).toordinal() if closing else cutoff.toordinal(),
        "LATE_ACTIVITIES_PCT": _ratio(len(late), len(activities)) * Decimal("100"),
        "MILESTONES_ON_TIME_PCT": _ratio(len(on_time_milestones), len(completed_milestones)) * Decimal("100"),
        "CLOSING_MILESTONE_DEVIATION": Decimal("0"),
        "CHANGE_REQUESTS": Decimal(len(changes)),
        "CHANGE_AVG_CYCLE_HOURS": _average(cycle_hours),
        "CHANGE_AVG_IMPACT_HOURS": Decimal("0"),
        "CHANGE_IMPACT_COST": sum((impact.delta_cost for impact in impacts), Decimal("0")),
        "CHANGE_IMPACT_DAYS": Decimal(sum(impact.delta_schedule_days for impact in impacts)),
        "CHANGE_SLA_BREACHES": Decimal("0"),
        "CHANGE_CONTINGENCY_CONSUMPTION": sum((impact.delta_contingency for impact in impacts), Decimal("0")),
        "CHANGE_ADOPTION_INDEX": Decimal("0"),
        "CHANGE_TRAINING_COVERAGE": Decimal("0"),
        **rates,
    }
    metrics.update(
        {
            "ADVANCE_GAP": metrics["AVANCE_REAL"] - metrics["AVANCE_PLAN"],
            "LATE_TASKS": _ratio(len(late), len(activities)),
            "MILESTONE_ON_TIME": _ratio(len(on_time_milestones), len(milestones)),
            "CLOSE_VARIANCE": metrics["FECHA_CIERRE_REAL"] - metrics["FECHA_CIERRE_BASE"],
        }
    )
    for index, value in enumerate(
        (
            metrics["CHANGE_REQUESTS"],
            metrics["CHANGE_APPROVAL_RATE"],
            metrics["CHANGE_REJECTION_RATE"],
            metrics["CHANGE_AVG_CYCLE_HOURS"],
            metrics["CHANGE_AVG_IMPACT_HOURS"],
            metrics["CHANGE_IMPACT_COST"],
            metrics["CHANGE_IMPACT_DAYS"],
            metrics["CHANGE_EVIDENCE_COMPLETE_PCT"],
            metrics["CHANGE_SLA_BREACHES"],
            metrics["CHANGE_CONTINGENCY_CONSUMPTION"],
            metrics["CHANGE_ADOPTION_INDEX"],
            metrics["CHANGE_TRAINING_COVERAGE"],
        ),
        start=1,
    ):
        metrics[f"VALOR_{index:02d}"] = value
    return metrics


def _ratio(numerator: int, denominator: int) -> Decimal:
    return Decimal(numerator) / Decimal(denominator) if denominator else Decimal("0")


def _average(values: list[Decimal]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values)) if values else Decimal("0")


def _planned_progress(elements: list[GanttElement], cutoff: date) -> Decimal:
    """Return the mean temporal progress of scheduled leaf work."""

    leaves = [element for element in elements if element.element_type.value == "SUBACTIVIDAD"]
    values = []
    for element in leaves:
        if not element.planned_start or not element.planned_finish or element.planned_finish <= element.planned_start:
            values.append(Decimal("1") if element.planned_finish and cutoff >= element.planned_finish else Decimal("0"))
            continue
        if cutoff <= element.planned_start:
            values.append(Decimal("0"))
        elif cutoff >= element.planned_finish:
            values.append(Decimal("1"))
        else:
            elapsed = (cutoff - element.planned_start).days
            duration = (element.planned_finish - element.planned_start).days
            values.append(Decimal(elapsed) / Decimal(duration))
    return _average(values) if values else Decimal("0")


@router.patch("/projects/{project_id}/kpis/{kpi_id}", tags=["kpis"])
def update_kpi(project_id: uuid.UUID, kpi_id: uuid.UUID, payload: KpiUpdate, session: Session = Depends(get_db), actor: Manager = None) -> dict[str, Any]:
    kpi = session.scalar(sa.select(Kpi).where(Kpi.id == kpi_id, Kpi.project_id == project_id))
    if kpi is None:
        raise ApiError("NOT_FOUND", "KPI no encontrado", 404)
    changes = payload.model_dump(exclude_unset=True)
    formula = changes.get("formula", kpi.formula)
    scope = changes.get("scope", kpi.scope)
    element_id = changes.get("element_id", kpi.element_id)
    _validate_formula(session, project_id, formula)
    _validate_kpi_scope(session, project_id, scope, element_id)
    if formula != kpi.formula:
        latest = session.scalar(sa.select(sa.func.max(KpiFormulaVersion.version)).where(KpiFormulaVersion.kpi_id == kpi.id)) or 0
        session.add(KpiFormulaVersion(kpi_id=kpi.id, version=int(latest) + 1, formula=formula, previous_formula=kpi.formula, changed_by=actor.id))
    for key, value in changes.items():
        setattr(kpi, key, value)
    session.commit()
    session.refresh(kpi)
    return _ok(_kpi(kpi))


@router.post("/projects/{project_id}/kpis/recalculate", tags=["kpis"])
def recalculate_kpis(project_id: uuid.UUID, cutoff_at: datetime | None = None, session: Session = Depends(get_db), _: Manager = None) -> dict[str, Any]:
    project = require_project(session, project_id)
    tasks, _, _ = _calculation_inputs(session, project)
    cutoff = project.cutoff_date or date.today()
    evm = DeterministicCalculationEngine(project_calendar(session, project)).calculate_evm(tasks, cutoff)
    metrics = {name: value for name, value in vars(evm).items()} if hasattr(evm, "__dict__") else {
        "BAC": evm.bac, "PV": evm.pv, "EV": evm.ev, "AC": evm.ac, "SPI": evm.spi, "CPI": evm.cpi,
        "SV": evm.sv, "CV": evm.cv, "EAC": evm.eac, "ETC": evm.etc, "VAC": evm.vac,
    }
    metrics.update(_project_kpi_metrics(session, project_id, cutoff))
    snapshot_at = cutoff_at or datetime.combine(cutoff, time.min, tzinfo=UTC)
    now = datetime.now(UTC)
    values: list[dict[str, Any]] = []
    for kpi in session.scalars(sa.select(Kpi).where(Kpi.project_id == project_id, Kpi.is_active.is_(True))).all():
        try:
            value = _formula_value(kpi.formula, metrics, _variable_codes(session, project_id))
        except ApiError:
            raise
        existing = session.scalar(sa.select(KpiValue).where(KpiValue.kpi_id == kpi.id, KpiValue.cutoff_at == snapshot_at))
        breakdown = {"formula": kpi.formula, "variables": {name: metrics.get(name) for name in formula_variables(kpi.formula)}}
        if existing is None:
            existing = KpiValue(kpi_id=kpi.id, cutoff_at=snapshot_at, value=value, breakdown=breakdown)
            session.add(existing)
        else:
            existing.value = value
            existing.breakdown = breakdown
            existing.calculated_at = now
        values.append({"kpi_id": kpi.id, "code": kpi.code, "value": value, "cutoff_at": snapshot_at, "breakdown": breakdown})
    session.commit()
    return _ok(values, cutoff_at=snapshot_at)


@router.get("/projects/{project_id}/kpis/snapshots", tags=["kpis"])
def list_kpi_snapshots(project_id: uuid.UUID, session: Session = Depends(get_db), _: CurrentUser = None) -> dict[str, Any]:
    require_project(session, project_id)
    rows = session.scalars(
        sa.select(KpiValue)
        .join(Kpi, KpiValue.kpi_id == Kpi.id)
        .where(Kpi.project_id == project_id)
        .order_by(KpiValue.cutoff_at.desc(), Kpi.code)
    ).all()
    return _ok(
        [
            {
                "id": row.id,
                "kpi_id": row.kpi_id,
                "cutoff_at": row.cutoff_at,
                "element_id": row.element_id,
                "value": row.value,
                "breakdown": row.breakdown,
                "calculated_at": row.calculated_at,
            }
            for row in rows
        ],
        total=len(rows),
    )


@router.get("/projects/{project_id}/kpis/{kpi_id}/versions", tags=["kpis"])
def list_kpi_formula_versions(project_id: uuid.UUID, kpi_id: uuid.UUID, session: Session = Depends(get_db), _: CurrentUser = None) -> dict[str, Any]:
    kpi = session.scalar(sa.select(Kpi).where(Kpi.id == kpi_id, Kpi.project_id == project_id))
    if kpi is None:
        raise ApiError("NOT_FOUND", "KPI no encontrado", 404)
    versions = session.scalars(
        sa.select(KpiFormulaVersion).where(KpiFormulaVersion.kpi_id == kpi_id).order_by(KpiFormulaVersion.version)
    ).all()
    return _ok(
        [
            {
                "id": version.id,
                "version": version.version,
                "formula": version.formula,
                "changed_by": version.changed_by,
                "changed_at": version.changed_at,
                "previous_formula": version.previous_formula,
            }
            for version in versions
        ],
        total=len(versions),
    )


def _formula_value(formula: str, metrics: dict[str, Any], variable_codes: tuple[str, ...] | None = None) -> Any:
    try:
        return evaluate_formula(formula, metrics, variable_codes)
    except KpiFormulaError as exc:
        raise ApiError("INVALID_KPI_FORMULA", str(exc)) from exc


@router.get("/projects/{project_id}/changes", tags=["changes"])
def list_changes(project_id: uuid.UUID, session: Session = Depends(get_db), _: CurrentUser = None) -> dict[str, Any]:
    require_project(session, project_id)
    changes = session.scalars(sa.select(ChangeRequest).where(ChangeRequest.project_id == project_id).order_by(ChangeRequest.created_at.desc())).all()
    return _ok([_change(change) for change in changes], total=len(changes))


def _change(change: ChangeRequest) -> dict[str, Any]:
    return {field: getattr(change, field) for field in ("id", "code", "title", "description", "change_type", "priority", "status", "requester_id", "responsible_id", "current_stage_id", "decided_at", "closed_at", "created_at", "updated_at")}


@router.post("/projects/{project_id}/changes", status_code=201, tags=["changes"])
def create_change(project_id: uuid.UUID, payload: ChangeCreate, session: Session = Depends(get_db), actor: CurrentUser = None) -> dict[str, Any]:
    require_project(session, project_id)
    change = ChangeRequest(project_id=project_id, requester_id=actor.id, **payload.model_dump())
    session.add(change)
    session.flush()
    stages = session.scalars(
        sa.select(ChangeStage)
        .where(ChangeStage.project_id == project_id, ChangeStage.is_active.is_(True))
        .order_by(ChangeStage.sequence)
    ).all()
    if not stages:
        stages = [
            ChangeStage(
                project_id=project_id,
                name=definition.name,
                sequence=definition.sequence,
                sla_hours=definition.sla_hours,
                is_active=True,
            )
            for definition in DEFAULT_CHANGE_STAGES
        ]
        session.add_all(stages)
        session.flush()
    change.current_stage_id = stages[0].id
    session.add_all(
        [
            ChangeRequestStage(
                request_id=change.id,
                stage_id=stage.id,
                status=ChangeStageStatus.ACTIVE if index == 0 else ChangeStageStatus.PENDING,
                entered_at=utc_now() if index == 0 else None,
            )
            for index, stage in enumerate(stages)
        ]
    )
    record_audit(
        session,
        user_id=actor.id,
        action="CREATE",
        entity_type="CHANGE_REQUEST",
        entity_id=change.id,
        after_data={"code": change.code, "status": change.status.value},
    )
    session.commit()
    session.refresh(change)
    return _ok(_change(change))


@router.post("/projects/{project_id}/changes/{change_id}/transition", tags=["changes"])
def transition_change(project_id: uuid.UUID, change_id: uuid.UUID, payload: ChangeTransitionCreate, session: Session = Depends(get_db), actor: Manager = None) -> dict[str, Any]:
    project = require_project(session, project_id)
    change = session.scalar(sa.select(ChangeRequest).where(ChangeRequest.id == change_id, ChangeRequest.project_id == project_id))
    if change is None:
        raise ApiError("NOT_FOUND", "Solicitud de cambio no encontrada", 404)
    if payload.to_stage_id is not None:
        expected = session.scalar(sa.select(ChangeStage).where(ChangeStage.id == payload.to_stage_id, ChangeStage.project_id == project_id))
        if expected is None:
            raise ApiError("NOT_FOUND", "Etapa de cambio no encontrada", 404)
    previous_status = change.status
    try:
        change = ChangeControlService(session, DeterministicCalculationEngine(project_calendar(session, project))).transition(
            change.id, payload.status, user_id=actor.id, comment=payload.comment
        )
    except F7Error as error:
        session.rollback()
        raise ApiError("INVALID_CHANGE_TRANSITION", str(error)) from error
    record_audit(
        session,
        user_id=actor.id,
        action="TRANSITION",
        entity_type="CHANGE_REQUEST",
        entity_id=change.id,
        before_data={"status": previous_status.value},
        after_data={"status": change.status.value, "comment": payload.comment},
    )
    session.commit()
    return _ok(_change(change))


@router.get("/projects/{project_id}/dashboard", tags=["dashboards"])
@router.get("/projects/{project_id}/dashboards", tags=["dashboards"])
def dashboard(project_id: uuid.UUID, session: Session = Depends(get_db), _: CurrentUser = None) -> dict[str, Any]:
    project = require_project(session, project_id)
    elements = project_elements(session, project_id)
    resources = project_resources(session, project_id)
    return _ok({
        "project": _project(project),
        "gantt": {"total": len(elements), "completed": sum(item.progress_pct == 100 for item in elements), "critical": sum(item.is_critical for item in elements)},
        "resources": {"total": len(resources)},
        "changes": {"open": session.scalar(sa.select(sa.func.count(ChangeRequest.id)).where(ChangeRequest.project_id == project_id, ChangeRequest.status == ChangeStatus.OPEN)) or 0},
        "kpis": {"total": session.scalar(sa.select(sa.func.count(Kpi.id)).where(Kpi.project_id == project_id)) or 0},
        "dashboards": {"total": session.scalar(sa.select(sa.func.count(Dashboard.id)).where(Dashboard.project_id == project_id)) or 0},
    })
