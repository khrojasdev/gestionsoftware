"""Conversor del libro original de Horizonte al formato canónico."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .models import CanonicalWorkbook
from .spreadsheet import parse_cell_date, read_xlsx, write_xlsx

ROLE_RATES: dict[str, int] = {
    "Jefe de Proyecto": 30000,
    "Desarrollador Backend": 24000,
    "Desarrollador de Integraciones": 26000,
    "Analista QA": 18500,
    "Desarrollador Frontend/Móvil": 24000,
    "Analista Funcional / de Negocio": 22000,
    "Diseñador UX/UI": 22000,
    "Analista de Datos / BI": 24000,
    "Arquitecto de Solución": 30000,
    "Ingeniero DevOps / Cloud": 26000,
    "Especialista Gestión del Cambio y Capacitación": 22000,
}


def convert_horizonte(source: Path) -> CanonicalWorkbook:
    """Convierte las hojas Cronograma, Planificación y Calendario de Horizonte."""

    source_sheets = read_xlsx(source)
    activities = _table(source_sheets.get("Actividades", []), 3)
    planning = _table(source_sheets.get("Planificación", []), 3)
    schedule = _table(source_sheets.get("Cronograma", []), 3)
    calendar = _table(source_sheets.get("Calendario", []), 12)
    summary = _table(source_sheets.get("Gantt resumen", []), 3)
    summary_names = {_text(row.get("EDT")): _text(row.get("Entregable / hito")) for row in summary}

    schedule_by_id = {_text(row.get("ID")): row for row in schedule}
    activity_by_id = {_text(row.get("ID Actividad")): row for row in activities}
    planning_by_id = {_text(row.get("ID")): row for row in planning}
    package_to_rows: dict[str, list[str]] = defaultdict(list)
    for identifier, row in schedule_by_id.items():
        package = _text(row.get("Paquete EDT"))
        if package and identifier:
            package_to_rows[package].append(identifier)

    gantt = _build_gantt(schedule_by_id, summary_names)
    _add_dependency_type_examples(gantt)
    resources, role_to_ids = _build_resources(planning_by_id)
    assignments = _build_assignments(planning_by_id, role_to_ids)
    criteria, milestone_tasks = _build_milestone_support(schedule_by_id, activity_by_id)
    return CanonicalWorkbook(
        {
            "Proyecto": _project_rows(),
            "Calendario": _calendar_rows(calendar),
            "Gantt": gantt,
            "Recursos": resources,
            "Asignaciones": assignments,
            "Criterios": criteria,
            "Hitos_Tareas": milestone_tasks,
        }
    )


def convert_horizonte_to_xlsx(source: Path, output: Path) -> CanonicalWorkbook:
    """Convierte y escribe el resultado únicamente en ``output`` (normalmente seeds/)."""

    workbook = convert_horizonte(source)
    write_xlsx(workbook.sheets, output)
    return workbook


def _table(rows: list[list[Any]], header_row: int) -> list[dict[str, Any]]:
    if len(rows) < header_row:
        return []
    headers = [str(value).strip() for value in rows[header_row - 1]]
    result: list[dict[str, Any]] = []
    for values in rows[header_row:]:
        row = {header: values[index] if index < len(values) else "" for index, header in enumerate(headers) if header}
        if any(_text(value) for value in row.values()):
            result.append(row)
    return result


def _build_gantt(schedule: dict[str, dict[str, Any]], summary_names: dict[str, str]) -> list[dict[str, Any]]:
    packages = sorted({_text(row.get("Paquete EDT")) for row in schedule.values() if _text(row.get("Paquete EDT"))}, key=_package_sort)
    stage_keys = sorted({".".join(package.split(".")[:2]) for package in packages}, key=_package_sort)
    rows: list[dict[str, Any]] = []
    for stage_key in stage_keys:
        stage_id = _stage_id(stage_key)
        rows.append(_gantt_row(stage_id, "ETAPA", summary_names.get(stage_key, f"Etapa {stage_key}"), ""))
        for package in [item for item in packages if item.startswith(f"{stage_key}.")]:
            activity_id = _activity_id(package)
            name = summary_names.get(package, f"Actividad {package}")
            rows.append(_gantt_row(activity_id, "ACTIVIDAD", name, stage_id))
            for identifier, source_row in schedule.items():
                if _text(source_row.get("Paquete EDT")) != package:
                    continue
                kind = "HITO" if identifier.startswith("H") else "SUBACTIVIDAD"
                planning_parent = activity_id
                predecessor = _dependency_text(source_row)
                start = parse_cell_date(source_row.get("Fecha inicio"))
                finish = parse_cell_date(source_row.get("Fecha fin"))
                duration = 0 if kind == "HITO" else _as_int(source_row.get("Duración (días)"))
                rows.append(
                    _gantt_row(
                        identifier,
                        kind,
                        _text(source_row.get("Actividad")),
                        planning_parent,
                        inicio_plan=start,
                        fin_plan=finish,
                        duracion_dias=duration,
                        predecesoras=predecessor,
                        avance_pct=_progress(source_row.get("% Avance")),
                    )
                )
    return rows


def _gantt_row(identifier: str, kind: str, name: str, parent: str, **values: Any) -> dict[str, Any]:
    row = {
        "id": identifier,
        "tipo": kind,
        "nombre": name or identifier,
        "padre_id": parent,
        "inicio_plan": "",
        "fin_plan": "",
        "duracion_dias": "",
        "predecesoras": "",
        "avance_pct": "",
        "inicio_real": "",
        "fin_real": "",
        "costo_real": "",
    }
    row.update(values)
    return row


def _add_dependency_type_examples(rows: list[dict[str, Any]]) -> None:
    """Conserva FS del origen y agrega ejemplos deterministas de los otros tipos."""

    replacements = {"A10": "H01SS", "A17": "A16FF", "A18": "A17SF"}
    for row in rows:
        identifier = _text(row.get("id"))
        if identifier in replacements and row.get("predecesoras"):
            predecessor = _text(row["predecesoras"]).split(";", 1)[0]
            predecessor_id = re.match(r"[A-Za-z0-9_-]+", predecessor)
            if predecessor_id:
                row["predecesoras"] = replacements[identifier]


def _build_resources(planning: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    requested: dict[str, int] = defaultdict(int)
    for row in planning.values():
        if _text(row.get("ID", "")).startswith("H"):
            continue
        roles = _roles(row.get("Recurso / Rol"))
        count = max(1, _as_int(row.get("N° recursos")) or len(roles) or 1)
        if len(roles) <= 1:
            for role in roles:
                requested[role] = max(requested[role], count)
        else:
            requested[roles[0]] = max(requested[roles[0]], count - len(roles) + 1)
            for role in roles[1:]:
                requested[role] = max(requested[role], 1)
    resources: list[dict[str, Any]] = []
    role_to_ids: dict[str, list[str]] = {}
    index = 1
    for role in sorted(requested):
        ids: list[str] = []
        for unit in range(1, requested[role] + 1):
            identifier = f"R{index:03d}"
            index += 1
            ids.append(identifier)
            resources.append(
                {
                    "recurso_id": identifier,
                    "nombre": f"{role} {unit}",
                    "tipo": "HUMANO",
                    "rol": role,
                    "tarifa": ROLE_RATES.get(role, 20000),
                    "unidad": "hora",
                    "capacidad_h_dia": 8,
                }
            )
        role_to_ids[role] = ids
    resources.extend(
        [
            {"recurso_id": "RE-EQ-001", "nombre": "Tablet de obra", "tipo": "EQUIPAMIENTO", "rol": "Dispositivo", "tarifa": 350000, "unidad": "unidad", "capacidad_h_dia": ""},
            {"recurso_id": "RE-INF-001", "nombre": "Infraestructura cloud", "tipo": "INFRAESTRUCTURA_LICENCIA", "rol": "Cloud", "tarifa": 1200000, "unidad": "mes", "capacidad_h_dia": ""},
            {"recurso_id": "RE-SVC-001", "nombre": "Servicio externo API compras", "tipo": "SERVICIO_EXTERNO", "rol": "Proveedor", "tarifa": 3000000, "unidad": "servicio", "capacidad_h_dia": ""},
        ]
    )
    return resources, role_to_ids


def _build_assignments(planning: dict[str, dict[str, Any]], role_to_ids: dict[str, list[str]]) -> list[dict[str, Any]]:
    assignments: list[dict[str, Any]] = []
    for task_id, row in planning.items():
        if not task_id.startswith("A"):
            continue
        roles = _roles(row.get("Recurso / Rol"))
        if not roles:
            continue
        count = max(1, _as_int(row.get("N° recursos")) or len(roles))
        slots: list[str] = []
        for role_index, role in enumerate(roles):
            role_count = count - len(roles) + 1 if role_index == 0 and len(roles) > 1 else 1
            slots.extend(role_to_ids.get(role, [])[: max(1, role_count)])
        effort = float(_as_int(row.get("Esfuerzo (hp)")) or 0)
        hours_each = effort / len(slots) if slots else 0
        h_day = _as_number(row.get("Disponibilidad (h/día)")) or 8
        for resource_id in slots:
            assignments.append(
                {
                    "tarea_id": task_id,
                    "recurso_id": resource_id,
                    "horas_planificadas": round(hours_each, 2),
                    "cantidad": "",
                    "h_dia": h_day,
                    "tarifa_override": "",
                }
            )
    return assignments


def _build_milestone_support(schedule: dict[str, dict[str, Any]], activities: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    criteria: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    for identifier, row in schedule.items():
        if not identifier.startswith("H"):
            continue
        source = activities.get(identifier, {})
        criteria.append(
            {
                "hito_id": identifier,
                "criterio_id": f"CR-{identifier}-01",
                "descripcion": _text(source.get("¿Terminada cuando...?")) or "Entregable aprobado",
                "forma_de_verificacion": "Revisión del acta y evidencia del entregable",
                "responsable": _text(source.get("Responsable / Rol")) or "Jefe de Proyecto",
            }
        )
        for predecessor in _predecessor_ids(row):
            links.append({"hito_id": identifier, "tarea_id": predecessor})
    return criteria, links


def _project_rows() -> list[dict[str, str]]:
    values = {
        "codigo": "HORIZONTE-CONECTA",
        "nombre": "Horizonte Conecta",
        "cliente": "Constructora Horizonte",
        "responsable": "Jefe de Proyecto",
        "fecha_inicio": "2026-10-05",
        "fecha_comprometida": "2027-07-12",
        "presupuesto": "212809000",
        "contingencia_pct": "10",
        "horas_por_dia": "8",
        "dias_laborales": "L-V",
        "fecha_corte": "2027-01-15",
    }
    return [{"clave": key, "valor": value} for key, value in values.items()]


def _calendar_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        if _text(row.get("Tipo")).lower() != "feriado":
            continue
        current = parse_cell_date(row.get("Desde"))
        if current:
            result.append({"fecha": current, "tipo": "FERIADO", "recurso_id": "", "descripcion": _text(row.get("Descripción"))})
    return result


def _dependency_text(row: dict[str, Any]) -> str:
    dependency_type = _text(row.get("Tipo")) or "FS"
    predecessors = _predecessor_ids(row)
    return ";".join(f"{item}{dependency_type}" for item in predecessors)


def _predecessor_ids(row: dict[str, Any]) -> list[str]:
    value = _text(row.get("Predecesora(s)"))
    if not value or value in {"—", "-", "–"}:
        return []
    return [item.strip() for item in re.split(r"[,;]", value) if item.strip()]


def _roles(value: Any) -> list[str]:
    return [item.strip() for item in _text(value).split("+") if item.strip() and item.strip().lower() != "hito"]


def _package_sort(value: str) -> tuple[int, ...]:
    return tuple(int(item) if item.isdigit() else 999 for item in value.split("."))


def _stage_id(package: str) -> str:
    return "E-" + package.replace(".", "-")


def _activity_id(package: str) -> str:
    return "AC-" + package.replace(".", "-")


def _progress(value: Any) -> int | str:
    text = _text(value).replace("%", "")
    return _as_number(text) if text else ""


def _as_int(value: Any) -> int | None:
    try:
        number = float(_text(value).replace(",", "."))
        return int(number) if number.is_integer() else None
    except (TypeError, ValueError):
        return None


def _as_number(value: Any) -> float | None:
    try:
        return float(_text(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()
