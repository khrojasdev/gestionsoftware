"""Reglas de validación de la plantilla canónica."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from .models import CANONICAL_COLUMNS, DATE_COLUMNS, CanonicalWorkbook, ValidationReport
from .spreadsheet import parse_cell_date

ELEMENT_TYPES = {"ETAPA", "ACTIVIDAD", "SUBACTIVIDAD", "HITO"}
RESOURCE_TYPES = {"HUMANO", "EQUIPAMIENTO", "INFRAESTRUCTURA_LICENCIA", "SERVICIO_EXTERNO"}
CALENDAR_TYPES = {"FERIADO", "NO_LABORABLE", "EXCEPCION_RECURSO"}
DEPENDENCY_TYPES = {"FS", "SS", "FF", "SF"}
DEP_ID_PATTERN = re.compile(r"^([A-Za-z0-9_-]+?)(FS|SS|FF|SF)?([+-]\d+)?$")


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace("%", "").replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int | None:
    number = _number(value)
    if number is None or not number.is_integer():
        return None
    return int(number)


def _business_days(start: date, finish: date, working_days: set[int], holidays: set[date]) -> int:
    if finish < start:
        return 0
    current = start
    count = 0
    while current <= finish:
        if current.weekday() in working_days and current not in holidays:
            count += 1
        current += timedelta(days=1)
    return count


def _working_days_from_project(rows: list[dict[str, Any]]) -> set[int]:
    values = {
        _text(row.get("valor")).upper()
        for row in rows
        if _text(row.get("clave")) == "dias_laborales"
    }
    value = next(iter(values), "L-V")
    if value in {"L-V", "LV", "LUN-VIE", "LUNES A VIERNES"}:
        return {0, 1, 2, 3, 4}
    numbers = {int(item) for item in re.findall(r"\d", value) if int(item) < 7}
    return numbers or {0, 1, 2, 3, 4}


def normalize_dates(workbook: CanonicalWorkbook, report: ValidationReport) -> None:
    for sheet, columns in DATE_COLUMNS.items():
        for row_index, row in enumerate(workbook.sheets.get(sheet, []), 2):
            for column in columns:
                raw = row.get(column, "")
                if raw in (None, ""):
                    row[column] = None
                    continue
                parsed = parse_cell_date(raw)
                if parsed is None:
                    report.add_error(sheet, row_index, column, "INVALID_DATE", f"Fecha inválida: {_text(raw)}")
                row[column] = parsed


def validate_workbook(workbook: CanonicalWorkbook) -> ValidationReport:
    """Valida y normaliza todas las hojas sin realizar persistencia."""

    report = ValidationReport()
    normalize_dates(workbook, report)
    _validate_headers(workbook, report)
    _validate_project(workbook, report)
    holidays = _validate_calendar(workbook, report)
    elements = _validate_gantt(workbook, report, holidays)
    resources = _validate_resources(workbook, report)
    _validate_assignments(workbook, report, elements, resources)
    _validate_criteria(workbook, report, elements)
    _validate_milestone_tasks(workbook, report, elements)
    _validate_predecessors(workbook, report, elements)
    return report


def _validate_headers(workbook: CanonicalWorkbook, report: ValidationReport) -> None:
    for sheet, _expected in CANONICAL_COLUMNS.items():
        if sheet not in workbook.sheets:
            report.add_error(sheet, 1, None, "MISSING_SHEET", "La hoja es obligatoria")
            continue
        # rows_to_sheets already projects known columns; this checks truly empty sheets.
        if not workbook.sheets[sheet] and sheet != "Hitos_Tareas":
            report.add_warning(sheet, 1, None, "EMPTY_SHEET", "La hoja no contiene filas de datos")


def _validate_project(workbook: CanonicalWorkbook, report: ValidationReport) -> None:
    project = {
        _text(row.get("clave")): _text(row.get("valor"))
        for row in workbook.sheets.get("Proyecto", [])
        if _text(row.get("clave"))
    }
    required = ("codigo", "nombre", "fecha_inicio", "fecha_comprometida", "presupuesto", "horas_por_dia", "dias_laborales")
    for key in required:
        if not project.get(key):
            report.add_error("Proyecto", None, "clave", "REQUIRED_PROJECT_VALUE", f"Falta el valor de proyecto '{key}'")
    for key in ("fecha_inicio", "fecha_comprometida"):
        if project.get(key) and parse_cell_date(project[key]) is None:
            report.add_error("Proyecto", None, "valor", "INVALID_PROJECT_DATE", f"Fecha inválida para '{key}'")
    for key in ("presupuesto", "contingencia_pct", "horas_por_dia"):
        if key in project and project[key] and _number(project[key]) is None:
            report.add_error("Proyecto", None, "valor", "INVALID_PROJECT_NUMBER", f"Número inválido para '{key}'")
    if _number(project.get("horas_por_dia")) is not None and _number(project["horas_por_dia"]) <= 0:
        report.add_error("Proyecto", None, "valor", "INVALID_WORKDAY", "horas_por_dia debe ser mayor que cero")


def _validate_calendar(workbook: CanonicalWorkbook, report: ValidationReport) -> set[date]:
    resource_ids = {_text(row.get("recurso_id")) for row in workbook.sheets.get("Recursos", [])}
    holidays: set[date] = set()
    for row_index, row in enumerate(workbook.sheets.get("Calendario", []), 2):
        kind = _text(row.get("tipo")).upper()
        if kind not in CALENDAR_TYPES:
            report.add_error("Calendario", row_index, "tipo", "INVALID_CALENDAR_TYPE", f"Tipo inválido: {kind}")
        current = row.get("fecha")
        if not isinstance(current, date):
            report.add_error("Calendario", row_index, "fecha", "REQUIRED_DATE", "La fecha es obligatoria")
        elif kind in {"FERIADO", "NO_LABORABLE"}:
            holidays.add(current)
        resource = _text(row.get("recurso_id"))
        if kind == "EXCEPCION_RECURSO" and resource and resource not in resource_ids:
            report.add_error("Calendario", row_index, "recurso_id", "UNKNOWN_RESOURCE", f"Recurso inexistente: {resource}")
    return holidays


def _validate_gantt(
    workbook: CanonicalWorkbook,
    report: ValidationReport,
    holidays: set[date],
) -> dict[str, dict[str, Any]]:
    rows = workbook.sheets.get("Gantt", [])
    elements: dict[str, dict[str, Any]] = {}
    working_days = _working_days_from_project(workbook.sheets.get("Proyecto", []))
    for row_index, row in enumerate(rows, 2):
        identifier = _text(row.get("id"))
        kind = _text(row.get("tipo")).upper()
        if not identifier:
            report.add_error("Gantt", row_index, "id", "REQUIRED_ID", "El ID es obligatorio")
            continue
        if identifier in elements:
            report.add_error("Gantt", row_index, "id", "DUPLICATE_ID", f"ID repetido: {identifier}")
        elements[identifier] = row
        if kind not in ELEMENT_TYPES:
            report.add_error("Gantt", row_index, "tipo", "INVALID_ELEMENT_TYPE", f"Tipo inválido: {kind}")
        if not _text(row.get("nombre")):
            report.add_error("Gantt", row_index, "nombre", "REQUIRED_NAME", "El nombre es obligatorio")
        _validate_parent_shape(row, row_index, elements, report)
        _normalize_duration(row, row_index, kind, working_days, holidays, report)
        _validate_progress(row, row_index, report)
    _validate_parent_references(rows, elements, report)
    return elements


def _validate_parent_shape(
    row: dict[str, Any], row_index: int, elements: dict[str, dict[str, Any]], report: ValidationReport
) -> None:
    kind = _text(row.get("tipo")).upper()
    parent = _text(row.get("padre_id"))
    if kind == "ETAPA" and parent:
        report.add_error("Gantt", row_index, "padre_id", "INVALID_ROOT_PARENT", "Una ETAPA no puede tener padre")
    if kind in {"ACTIVIDAD", "SUBACTIVIDAD", "HITO"} and not parent:
        report.add_error("Gantt", row_index, "padre_id", "REQUIRED_PARENT", f"{kind} requiere padre_id")


def _normalize_duration(
    row: dict[str, Any],
    row_index: int,
    kind: str,
    working_days: set[int],
    holidays: set[date],
    report: ValidationReport,
) -> None:
    start = row.get("inicio_plan")
    finish = row.get("fin_plan")
    duration = _integer(row.get("duracion_dias"))
    provided = sum(value is not None for value in (start, finish, duration))
    if kind in {"ETAPA", "ACTIVIDAD"}:
        if provided:
            report.add_error("Gantt", row_index, "duracion_dias", "PARENT_DATES_FORBIDDEN", "ETAPA y ACTIVIDAD consolidan fechas y costos")
        return
    if kind == "HITO":
        if duration not in (None, 0):
            report.add_error("Gantt", row_index, "duracion_dias", "MILESTONE_DURATION", "Un HITO debe tener duración 0")
        if start is not None and finish is not None and start != finish:
            report.add_error("Gantt", row_index, "fin_plan", "MILESTONE_DATES", "Un HITO debe iniciar y terminar el mismo día")
        row["duracion_dias"] = 0
        if start is None and finish is not None:
            row["inicio_plan"] = finish
        if finish is None and start is not None:
            row["fin_plan"] = start
        return
    if provided < 2:
        report.add_error("Gantt", row_index, None, "TWO_OF_THREE_REQUIRED", "Se requieren dos de inicio_plan, fin_plan y duracion_dias")
        return
    if duration is not None and duration <= 0:
        report.add_error("Gantt", row_index, "duracion_dias", "INVALID_DURATION", "La duración debe ser mayor que cero")
    if start is not None and finish is not None and finish < start:
        report.add_error("Gantt", row_index, "fin_plan", "DATE_ORDER", "fin_plan debe ser posterior o igual a inicio_plan")
    if start is not None and finish is not None:
        expected = _business_days(start, finish, working_days, holidays)
        if duration is None:
            row["duracion_dias"] = expected
        elif expected != duration:
            report.add_error("Gantt", row_index, "duracion_dias", "DURATION_CALENDAR_MISMATCH", f"Duración {duration} no coincide con {expected} días hábiles")
    elif start is not None and duration is not None:
        row["fin_plan"] = _add_working_days(start, duration - 1, working_days, holidays)
    elif finish is not None and duration is not None:
        row["inicio_plan"] = _subtract_working_days(finish, duration - 1, working_days, holidays)


def _validate_progress(row: dict[str, Any], row_index: int, report: ValidationReport) -> None:
    value = _number(row.get("avance_pct"))
    if value is not None and not 0 <= value <= 100:
        report.add_error("Gantt", row_index, "avance_pct", "INVALID_PROGRESS", "avance_pct debe estar entre 0 y 100")


def _validate_parent_references(rows: list[dict[str, Any]], elements: dict[str, dict[str, Any]], report: ValidationReport) -> None:
    expected_parent = {"ACTIVIDAD": {"ETAPA"}, "SUBACTIVIDAD": {"ACTIVIDAD"}, "HITO": {"ACTIVIDAD", "ETAPA"}}
    for row_index, row in enumerate(rows, 2):
        kind = _text(row.get("tipo")).upper()
        parent_id = _text(row.get("padre_id"))
        if not parent_id:
            continue
        parent = elements.get(parent_id)
        if parent is None:
            report.add_error("Gantt", row_index, "padre_id", "UNKNOWN_PARENT", f"Padre inexistente: {parent_id}")
        elif kind in expected_parent and _text(parent.get("tipo")).upper() not in expected_parent[kind]:
            report.add_error("Gantt", row_index, "padre_id", "INVALID_HIERARCHY", f"{kind} no puede depender de {_text(parent.get('tipo'))}")


def _add_working_days(start: date, offset: int, working_days: set[int], holidays: set[date]) -> date:
    current = start
    remaining = offset
    while remaining:
        current += timedelta(days=1)
        if current.weekday() in working_days and current not in holidays:
            remaining -= 1
    while current.weekday() not in working_days or current in holidays:
        current += timedelta(days=1)
    return current


def _subtract_working_days(finish: date, offset: int, working_days: set[int], holidays: set[date]) -> date:
    current = finish
    remaining = offset
    while remaining:
        current -= timedelta(days=1)
        if current.weekday() in working_days and current not in holidays:
            remaining -= 1
    while current.weekday() not in working_days or current in holidays:
        current -= timedelta(days=1)
    return current


def _validate_resources(workbook: CanonicalWorkbook, report: ValidationReport) -> dict[str, dict[str, Any]]:
    resources: dict[str, dict[str, Any]] = {}
    for row_index, row in enumerate(workbook.sheets.get("Recursos", []), 2):
        identifier = _text(row.get("recurso_id"))
        kind = _text(row.get("tipo")).upper()
        if not identifier:
            report.add_error("Recursos", row_index, "recurso_id", "REQUIRED_ID", "recurso_id es obligatorio")
        elif identifier in resources:
            report.add_error("Recursos", row_index, "recurso_id", "DUPLICATE_ID", f"Recurso repetido: {identifier}")
        resources[identifier] = row
        if kind not in RESOURCE_TYPES:
            report.add_error("Recursos", row_index, "tipo", "INVALID_RESOURCE_TYPE", f"Tipo inválido: {kind}")
        if _number(row.get("tarifa")) is None or _number(row.get("tarifa")) < 0:
            report.add_error("Recursos", row_index, "tarifa", "INVALID_RATE", "tarifa debe ser un número no negativo")
        if kind == "HUMANO" and (_number(row.get("capacidad_h_dia")) is None or _number(row.get("capacidad_h_dia")) <= 0):
            report.add_error("Recursos", row_index, "capacidad_h_dia", "INVALID_CAPACITY", "Un recurso humano requiere capacidad_h_dia positiva")
    return resources


def _validate_assignments(
    workbook: CanonicalWorkbook,
    report: ValidationReport,
    elements: dict[str, dict[str, Any]],
    resources: dict[str, dict[str, Any]],
) -> None:
    assigned_tasks: set[str] = set()
    daily_by_resource: dict[str, dict[date, float]] = defaultdict(lambda: defaultdict(float))
    for row_index, row in enumerate(workbook.sheets.get("Asignaciones", []), 2):
        task_id = _text(row.get("tarea_id"))
        resource_id = _text(row.get("recurso_id"))
        task = elements.get(task_id)
        resource = resources.get(resource_id)
        if task is None:
            report.add_error("Asignaciones", row_index, "tarea_id", "UNKNOWN_TASK", f"Tarea inexistente: {task_id}")
        elif _text(task.get("tipo")).upper() != "SUBACTIVIDAD":
            report.add_error("Asignaciones", row_index, "tarea_id", "INVALID_TASK_TYPE", "Solo se asignan SUBACTIVIDAD")
        if resource is None:
            report.add_error("Asignaciones", row_index, "recurso_id", "UNKNOWN_RESOURCE", f"Recurso inexistente: {resource_id}")
        amount = _number(row.get("horas_planificadas")) if resource and _text(resource.get("tipo")).upper() == "HUMANO" else _number(row.get("cantidad"))
        if amount is None or amount <= 0:
            column = "horas_planificadas" if resource and _text(resource.get("tipo")).upper() == "HUMANO" else "cantidad"
            report.add_error("Asignaciones", row_index, column, "INVALID_ASSIGNMENT_AMOUNT", "La cantidad/hora debe ser mayor que cero")
        h_day = _number(row.get("h_dia"))
        if h_day is not None and h_day <= 0:
            report.add_error("Asignaciones", row_index, "h_dia", "INVALID_DAILY_HOURS", "h_dia debe ser mayor que cero")
        if resource and task and _text(resource.get("tipo")).upper() == "HUMANO" and h_day:
            start, finish = task.get("inicio_plan"), task.get("fin_plan")
            if isinstance(start, date) and isinstance(finish, date):
                current = start
                while current <= finish:
                    if current.weekday() < 5:
                        daily_by_resource[resource_id][current] += h_day
                    current += timedelta(days=1)
        assigned_tasks.add(task_id)
    for identifier, row in elements.items():
        if _text(row.get("tipo")).upper() == "SUBACTIVIDAD" and identifier not in assigned_tasks:
            report.add_warning("Asignaciones", None, "tarea_id", "TASK_WITHOUT_RESOURCE", f"Tarea sin recurso: {identifier}")
    for resource_id, days in daily_by_resource.items():
        capacity = _number(resources[resource_id].get("capacidad_h_dia"))
        overloaded = sorted(day for day, total in days.items() if capacity and total > capacity)
        if overloaded:
            peak = max(days[day] for day in overloaded)
            report.add_warning(
                "Asignaciones",
                None,
                "h_dia",
                "OVERALLOCATION",
                f"Sobreasignación de {resource_id}: hasta {peak:g} h/día de {capacity:g} "
                f"({len(overloaded)} días, desde {overloaded[0].strftime('%d-%m-%Y')})",
            )


def _validate_criteria(workbook: CanonicalWorkbook, report: ValidationReport, elements: dict[str, dict[str, Any]]) -> None:
    milestones = {identifier for identifier, row in elements.items() if _text(row.get("tipo")).upper() == "HITO"}
    criteria_by_milestone: dict[str, int] = defaultdict(int)
    seen: set[str] = set()
    for row_index, row in enumerate(workbook.sheets.get("Criterios", []), 2):
        hito_id = _text(row.get("hito_id"))
        criterion_id = _text(row.get("criterio_id"))
        if hito_id not in milestones:
            report.add_error("Criterios", row_index, "hito_id", "UNKNOWN_MILESTONE", f"Hito inexistente: {hito_id}")
        if not criterion_id:
            report.add_error("Criterios", row_index, "criterio_id", "REQUIRED_ID", "criterio_id es obligatorio")
        elif criterion_id in seen:
            report.add_error("Criterios", row_index, "criterio_id", "DUPLICATE_ID", f"Criterio repetido: {criterion_id}")
        if not _text(row.get("descripcion")):
            report.add_error("Criterios", row_index, "descripcion", "REQUIRED_DESCRIPTION", "La descripción del criterio es obligatoria")
        if not _text(row.get("forma_de_verificacion")):
            report.add_error("Criterios", row_index, "forma_de_verificacion", "REQUIRED_VERIFICATION", "La forma de verificación es obligatoria")
        seen.add(criterion_id)
        criteria_by_milestone[hito_id] += 1
    for milestone in milestones:
        if criteria_by_milestone[milestone] == 0:
            report.add_error("Criterios", None, "hito_id", "MISSING_MILESTONE_CRITERIA", f"El hito {milestone} requiere al menos un criterio")


def _validate_milestone_tasks(workbook: CanonicalWorkbook, report: ValidationReport, elements: dict[str, dict[str, Any]]) -> None:
    for row_index, row in enumerate(workbook.sheets.get("Hitos_Tareas", []), 2):
        milestone = _text(row.get("hito_id"))
        task = _text(row.get("tarea_id"))
        if _text(elements.get(milestone, {}).get("tipo")).upper() != "HITO":
            report.add_error("Hitos_Tareas", row_index, "hito_id", "UNKNOWN_MILESTONE", f"No es un hito: {milestone}")
        if task not in elements:
            report.add_error("Hitos_Tareas", row_index, "tarea_id", "UNKNOWN_TASK", f"Elemento inexistente: {task}")


def _parse_dependency(token: str, known_ids: set[str]) -> tuple[str, str, int] | None:
    clean = token.strip().replace(" ", "")
    for identifier in sorted(known_ids, key=len, reverse=True):
        if clean == identifier:
            return identifier, "FS", 0
        if not clean.startswith(identifier):
            continue
        suffix = clean[len(identifier) :]
        match = re.fullmatch(r"(FS|SS|FF|SF)?([+-]\d+)?", suffix)
        if match:
            return identifier, match.group(1) or "FS", int(match.group(2) or 0)
    return None


def _validate_predecessors(workbook: CanonicalWorkbook, report: ValidationReport, elements: dict[str, dict[str, Any]]) -> None:
    edges: dict[str, list[str]] = defaultdict(list)
    known_ids = set(elements)
    for row_index, row in enumerate(workbook.sheets.get("Gantt", []), 2):
        current = _text(row.get("id"))
        raw = _text(row.get("predecesoras"))
        if not raw:
            continue
        for token in raw.split(";"):
            parsed = _parse_dependency(token, known_ids)
            if parsed is None:
                report.add_error("Gantt", row_index, "predecesoras", "INVALID_DEPENDENCY", f"Dependencia inválida: {token.strip()}")
                continue
            predecessor, dependency_type, _ = parsed
            if dependency_type not in DEPENDENCY_TYPES:
                report.add_error("Gantt", row_index, "predecesoras", "INVALID_DEPENDENCY_TYPE", f"Tipo inválido: {dependency_type}")
            edges[predecessor].append(current)
    cycle = _find_cycle(edges, known_ids)
    if cycle:
        report.add_error("Gantt", None, "predecesoras", "DEPENDENCY_CYCLE", "Ciclo detectado: " + " → ".join(cycle))


def _find_cycle(edges: dict[str, list[str]], nodes: set[str]) -> list[str] | None:
    visited: set[str] = set()
    active: list[str] = []
    active_set: set[str] = set()

    def visit(node: str) -> list[str] | None:
        if node in active_set:
            return active[active.index(node) :] + [node]
        if node in visited:
            return None
        visited.add(node)
        active.append(node)
        active_set.add(node)
        for successor in edges.get(node, []):
            cycle = visit(successor)
            if cycle:
                return cycle
        active.pop()
        active_set.remove(node)
        return None

    for node in sorted(nodes):
        cycle = visit(node)
        if cycle:
            return cycle
    return None
