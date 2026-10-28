"""Conversor del libro original de Horizonte al formato canónico de Carta Gantt.

El libro de trabajo del curso (``Caso3_Horizonte_Planificacion_Gantt.xlsx``)
trae el cronograma en las hojas *Actividades*, *Planificación*, *Cronograma* y
*Calendario*.  Este módulo lo transforma a la plantilla canónica de Trazo:

* La jerarquía etapa → actividad → subactividad se deriva del código EDT
  (``1.x`` → etapa, ``1.x.y`` → actividad, ``Axx``/``Hxx`` → subactividad/hito).
* Los recursos humanos se crean por persona según la dotación del documento de
  trabajo (sección 14) y sus tarifas oficiales; los recursos no laborales se
  agregan con sus cantidades y costos unitarios.
* Se agregan tres vínculos SS, FF y SF coherentes con el cronograma para cubrir
  los cuatro tipos de dependencia que exige la rúbrica sin mover fechas.
* Se simula el avance real a la fecha de corte 15-01-2027 (datos de demo).

El archivo original nunca se modifica: solo se lee.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from .models import CanonicalWorkbook
from .spreadsheet import parse_cell_date, read_xlsx, write_xlsx

# Tarifas por hora del Documento de Trabajo (sección 14 · Recursos y presupuesto).
ROLE_RATES: dict[str, int] = {
    "Jefe de Proyecto": 30000,
    "Analista Funcional / de Negocio": 22000,
    "Arquitecto de Solución": 32000,
    "Diseñador UX/UI": 21000,
    "Desarrollador Backend": 24000,
    "Desarrollador Frontend/Móvil": 24000,
    "Desarrollador de Integraciones": 26000,
    "Analista de Datos / BI": 23000,
    "Analista QA": 18500,
    "Ingeniero DevOps / Cloud": 27000,
    "Especialista Gestión del Cambio y Capacitación": 19500,
}

# Dotación por rol (misma tabla).
ROLE_HEADCOUNT: dict[str, int] = {
    "Jefe de Proyecto": 1,
    "Analista Funcional / de Negocio": 1,
    "Arquitecto de Solución": 1,
    "Diseñador UX/UI": 1,
    "Desarrollador Backend": 2,
    "Desarrollador Frontend/Móvil": 2,
    "Desarrollador de Integraciones": 1,
    "Analista de Datos / BI": 1,
    "Analista QA": 2,
    "Ingeniero DevOps / Cloud": 1,
    "Especialista Gestión del Cambio y Capacitación": 1,
}

ROLE_PREFIX: dict[str, str] = {
    "Jefe de Proyecto": "JP",
    "Analista Funcional / de Negocio": "AF",
    "Arquitecto de Solución": "AR",
    "Diseñador UX/UI": "UX",
    "Desarrollador Backend": "BE",
    "Desarrollador Frontend/Móvil": "FE",
    "Desarrollador de Integraciones": "IN",
    "Analista de Datos / BI": "BI",
    "Analista QA": "QA",
    "Ingeniero DevOps / Cloud": "DO",
    "Especialista Gestión del Cambio y Capacitación": "GC",
}

# Recursos no laborales (tipo, unidad, cantidad, costo unitario, actividades).
NON_LABOR: tuple[tuple[str, str, str, str, float, int, tuple[str, ...]], ...] = (
    ("NL-01", "Infraestructura cloud (dev, QA y producción)", "INFRAESTRUCTURA_LICENCIA", "mes", 10, 850000, ("A13", "A28")),
    ("NL-02", "Licencias de herramientas del proyecto", "INFRAESTRUCTURA_LICENCIA", "usuario-mes", 140, 22000, ("A03",)),
    ("NL-03", "Licencias de tablero BI (piloto)", "INFRAESTRUCTURA_LICENCIA", "usuario-mes", 175, 13000, ("A25", "A26", "A40")),
    ("NL-04", "Tablets rugerizadas para obra", "EQUIPAMIENTO", "unidad", 12, 480000, ("A34",)),
    ("NL-05", "Kits de conectividad para obras", "EQUIPAMIENTO", "kit", 3, 950000, ("A34",)),
    ("NL-06", "Soporte del proveedor del sistema de compras", "SERVICIO_EXTERNO", "hora", 120, 35000, ("A10", "A17")),
    ("NL-07", "Soporte del proveedor del ERP", "SERVICIO_EXTERNO", "hora", 60, 38000, ("A18",)),
    ("NL-08", "Prueba de seguridad externa (ethical hacking)", "SERVICIO_EXTERNO", "servicio", 1, 4800000, ("A32",)),
    ("NL-09", "Traslados y viáticos a obras piloto", "SERVICIO_EXTERNO", "global", 1, 3600000, ("A05", "A12", "A35", "A37", "A40")),
)

STAGE_NAMES: dict[str, str] = {
    "1.1": "Gestión del proyecto",
    "1.2": "Diagnóstico y requisitos",
    "1.3": "Diseño de la solución",
    "1.4": "Plataforma base",
    "1.5": "Integraciones corporativas",
    "1.6": "Release 1: operación de obra",
    "1.7": "Release 2: control económico",
    "1.8": "Pruebas y calidad",
    "1.9": "Piloto y gestión del cambio",
    "1.10": "Transición a operación",
}

PACKAGE_NAMES: dict[str, str] = {
    "1.1.1": "Inicio y planificación",
    "1.1.2": "Seguimiento y control",
    "1.1.3": "Cierre del proyecto",
    "1.2.1": "Diagnóstico de procesos actuales",
    "1.2.2": "Requisitos, indicadores y backlog",
    "1.3.1": "Arquitectura, integraciones y datos",
    "1.3.2": "Diseño UX/UI",
    "1.4.1": "Ambientes cloud",
    "1.4.2": "Núcleo y app móvil offline",
    "1.5.1": "Identidad y repositorio Microsoft",
    "1.5.2": "Sistema de compras y ERP",
    "1.6.1": "Módulo de avance de obra",
    "1.6.2": "Módulo de observaciones técnicas",
    "1.6.3": "Módulo de planos vigentes",
    "1.7.1": "Módulo de materiales",
    "1.7.2": "Módulo de subcontratos y estados de pago",
    "1.7.3": "Tablero ejecutivo",
    "1.8.1": "Plan de pruebas y calidad por sprint",
    "1.8.2": "Pruebas de Release 1",
    "1.8.3": "Pruebas de Release 2",
    "1.9.1": "Gestión del cambio y preparación de obras",
    "1.9.2": "Puesta en marcha de Release 1",
    "1.9.3": "Puesta en marcha de Release 2",
    "1.9.4": "Evaluación del piloto",
    "1.10.1": "Documentación y traspaso a TI",
}

# Vínculos SS / FF / SF que respetan las fechas originales del cronograma.
DEPENDENCY_OVERRIDES: dict[str, str] = {
    "A03": "A02;A40FF",  # el seguimiento (nivel de esfuerzo) termina junto con A40
    "A20": "H04;A19SS",  # el registro móvil arranca junto con la importación de programación
    "A37": "H06;A31SF",  # la operación asistida R1 no termina antes de iniciar pruebas R2
}

CUTOFF = date(2027, 1, 15)
IN_PROGRESS: dict[str, float] = {
    "A03": 30, "A17": 5, "A19": 20, "A20": 15, "A21": 25, "A25": 10, "A28": 10, "A34": 20,
}
ACTUAL_FINISH: dict[str, date] = {"A14": date(2027, 1, 6)}
COST_FACTOR: dict[str, float] = {
    "A05": 1.08, "A07": 1.05, "A10": 0.95, "A11": 1.03, "A12": 0.98, "A13": 1.06,
    "A14": 1.07, "A15": 1.02, "A16": 1.04, "A17": 1.12, "A21": 1.10,
}

CHANGE_STAGES: tuple[tuple[str, int], ...] = (
    ("Registro", 24),
    ("Revisión inicial", 24),
    ("Clasificación y prioridad", 24),
    ("Análisis de impacto", 72),
    ("Revisión del comité", 72),
    ("Decisión", 24),
    ("Planificación del cambio", 48),
    ("Implementación", 120),
    ("Verificación", 48),
    ("Cierre y línea base", 24),
)

KPI_COLUMNS = ("codigo", "nombre", "formula", "ambito", "categoria", "meta", "verde", "amarillo", "unidad", "adicional", "descripcion")

PROJECT_KPIS: tuple[tuple[Any, ...], ...] = (
    ("P01", "Índice de desempeño del cronograma (SPI)", "EV / PV", "PROYECTO", "PROYECTO", 1, 0.95, 0.90, "índice", "", "Valor ganado sobre valor planificado a la fecha de corte."),
    ("P02", "Índice de desempeño de costo (CPI)", "EV / AC", "PROYECTO", "PROYECTO", 1, 0.95, 0.90, "índice", "", "Valor ganado sobre costo real a la fecha de corte."),
    ("P03", "Variación del cronograma (SV)", "EV - PV", "PROYECTO", "PROYECTO", 0, 0, -2000000, "CLP", "", "Diferencia entre valor ganado y valor planificado."),
    ("P04", "Variación de costo (CV)", "EV - AC", "PROYECTO", "PROYECTO", 0, 0, -2000000, "CLP", "", "Diferencia entre valor ganado y costo real."),
    ("P05", "Desviación de avance físico", "AVANCE_REAL - AVANCE_PLAN", "PROYECTO", "PROYECTO", 0, -2, -5, "pp", "", "Avance real menos avance planificado, en puntos porcentuales."),
    ("P06", "Actividades atrasadas", "count(ACTIVIDADES_ATRASADAS) / count(ACTIVIDADES) * 100", "PROYECTO", "PROYECTO", 0, 10, 20, "%", "", "Subactividades iniciadas o vencidas con avance bajo lo planificado."),
    ("P07", "Hitos cumplidos a tiempo", "MILESTONES_ON_TIME_PCT", "HITO", "PROYECTO", 100, 90, 75, "%", "", "Hitos cumplidos en o antes de su fecha base, sobre hitos cumplidos."),
    ("P08", "Desviación del hito de cierre", "CLOSING_MILESTONE_DEVIATION", "HITO", "PROYECTO", 0, 0, 10, "días", "", "Días hábiles entre la fecha proyectada y la fecha base del cierre."),
)

CHANGE_KPIS: tuple[tuple[Any, ...], ...] = (
    ("C01", "Solicitudes registradas", "CHANGE_REQUESTS", "PROYECTO", "CAMBIO", "", "", "", "n°", "", "Total de solicitudes de cambio del proyecto."),
    ("C02", "Tasa de aprobación", "CHANGE_APPROVAL_RATE * 100", "PROYECTO", "CAMBIO", "", "", "", "%", "", "Aprobadas sobre decididas."),
    ("C03", "Tasa de rechazo", "CHANGE_REJECTION_RATE * 100", "PROYECTO", "CAMBIO", "", "", "", "%", "", "Rechazadas sobre decididas."),
    ("C04", "Tiempo medio de ciclo", "CHANGE_AVG_CYCLE_HOURS / 24", "PROYECTO", "CAMBIO", 7, 7, 10, "días", "", "Promedio de días entre registro y cierre de las solicitudes cerradas."),
    ("C05", "Tiempo medio de evaluación de impacto", "CHANGE_AVG_IMPACT_HOURS / 24", "PROYECTO", "CAMBIO", 3, 3, 5, "días", "", "Promedio de días entre registro y primer análisis de impacto."),
    ("C06", "Impacto acumulado en costo", "CHANGE_IMPACT_COST", "PROYECTO", "CAMBIO", "", "", "", "CLP", "", "Suma del delta de costo de los cambios aprobados."),
    ("C07", "Impacto acumulado en plazo", "CHANGE_IMPACT_DAYS", "PROYECTO", "CAMBIO", 0, 8, 16, "días", "", "Suma del delta de plazo de los cambios aprobados."),
    ("C08", "Solicitudes con evidencia completa", "CHANGE_EVIDENCE_COMPLETE_PCT * 100", "PROYECTO", "CAMBIO", 100, 100, 80, "%", "", "Solicitudes con al menos una evidencia sobre el total."),
    ("C09", "Solicitudes fuera de SLA", "CHANGE_SLA_BREACHES", "PROYECTO", "CAMBIO", 0, 0, 1, "n°", "", "Solicitudes abiertas cuya etapa activa superó su SLA."),
    ("C10", "Consumo de contingencia", "CHANGE_CONTINGENCY_CONSUMPTION", "PROYECTO", "CAMBIO", 0, 30, 50, "%", "Sí", "Costo de cambios aprobados sobre la contingencia del proyecto."),
    ("C11", "Índice de adopción", "CHANGE_ADOPTION_INDEX", "PROYECTO", "CAMBIO", 80, 80, 60, "%", "Sí", "Usuarios activos sobre usuarios capacitados (variable manual)."),
    ("C12", "Cobertura de capacitación", "CHANGE_TRAINING_COVERAGE", "PROYECTO", "CAMBIO", 100, 90, 70, "%", "Sí", "Usuarios capacitados sobre usuarios objetivo (variable manual)."),
)


def kpi_rows(definitions: tuple[tuple[Any, ...], ...]) -> list[dict[str, Any]]:
    """Return KPI definitions as rows of the supplemental KPI sheets."""

    return [dict(zip(KPI_COLUMNS, values, strict=True)) for values in definitions]


def change_stage_rows() -> list[dict[str, Any]]:
    return [
        {"id": f"CS{index:02d}", "nombre": name, "secuencia": index, "sla_horas": sla}
        for index, (name, sla) in enumerate(CHANGE_STAGES, start=1)
    ]


def dashboard_rows() -> list[dict[str, Any]]:
    return [
        {"id": "DB-PROYECTO", "nombre": "Tablero del proyecto", "tipo": "PROYECTO", "kpis": ",".join(row[0] for row in PROJECT_KPIS)},
        {"id": "DB-CAMBIO", "nombre": "Tablero de gestión del cambio", "tipo": "CAMBIO", "kpis": ",".join(row[0] for row in CHANGE_KPIS)},
    ]


def convert_horizonte(source: Path) -> CanonicalWorkbook:
    """Convierte las hojas del libro original de Horizonte a la plantilla."""

    source_sheets = read_xlsx(source)
    activities = _table(source_sheets.get("Actividades", []), 3)
    planning = _table(source_sheets.get("Planificación", []), 3)
    schedule = _table(source_sheets.get("Cronograma", []), 3)
    calendar = _table(source_sheets.get("Calendario", []), 12)
    if not schedule:
        raise ValueError("El libro no contiene la hoja 'Cronograma' del formato Horizonte")

    schedule_by_id = {_text(row.get("ID")): row for row in schedule if _text(row.get("ID"))}
    activity_by_id = {_text(row.get("ID Actividad")): row for row in activities}
    planning_by_id = {_text(row.get("ID")): row for row in planning}

    resources, role_ids = _build_resources()
    assignments = _build_assignments(planning_by_id, role_ids)
    task_costs = _task_planned_costs(assignments, resources)
    gantt = _build_gantt(schedule_by_id, task_costs)
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
            "Etapas_Cambio": change_stage_rows(),
            "KPI_Proyecto_Hitos": kpi_rows(PROJECT_KPIS),
            "KPI_Cambio": kpi_rows(CHANGE_KPIS),
            "Tableros": dashboard_rows(),
        }
    )


def is_horizonte_workbook(raw: dict[str, list[list[Any]]]) -> bool:
    """Detect the course workbook format (it has a 'Cronograma' sheet)."""

    return "Cronograma" in raw and "Gantt" not in raw


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


def _build_gantt(schedule: dict[str, dict[str, Any]], task_costs: dict[str, float]) -> list[dict[str, Any]]:
    packages = sorted({_text(row.get("Paquete EDT")) for row in schedule.values() if _text(row.get("Paquete EDT"))}, key=_package_sort)
    stage_keys = sorted({".".join(package.split(".")[:2]) for package in packages}, key=_package_sort)
    rows: list[dict[str, Any]] = []
    for stage_key in stage_keys:
        stage_id = _stage_id(stage_key)
        rows.append(_gantt_row(stage_id, "ETAPA", STAGE_NAMES.get(stage_key, f"Etapa {stage_key}"), ""))
        for package in [item for item in packages if ".".join(item.split(".")[:2]) == stage_key]:
            activity_id = _activity_id(package)
            rows.append(_gantt_row(activity_id, "ACTIVIDAD", PACKAGE_NAMES.get(package, f"Actividad {package}"), stage_id))
            members = [identifier for identifier, row in schedule.items() if _text(row.get("Paquete EDT")) == package]
            for identifier in sorted(members, key=lambda item: (parse_cell_date(schedule[item].get("Fecha inicio")) or date.max, _leaf_sort(item))):
                source_row = schedule[identifier]
                kind = "HITO" if identifier.startswith("H") else "SUBACTIVIDAD"
                start = parse_cell_date(source_row.get("Fecha inicio"))
                finish = parse_cell_date(source_row.get("Fecha fin"))
                duration = 0 if kind == "HITO" else _as_int(source_row.get("Duración (días)"))
                values: dict[str, Any] = {
                    "inicio_plan": start,
                    "fin_plan": finish,
                    "duracion_dias": duration,
                    "predecesoras": DEPENDENCY_OVERRIDES.get(identifier, _dependency_text(source_row)),
                }
                values.update(_progress_values(identifier, kind, start, finish, task_costs.get(identifier, 0.0)))
                rows.append(_gantt_row(identifier, kind, _text(source_row.get("Actividad")).removeprefix("Hito: "), activity_id, **values))
    return rows


def _progress_values(identifier: str, kind: str, start: date | None, finish: date | None, planned_cost: float) -> dict[str, Any]:
    """Simulated status at the demo cut-off date (15-01-2027)."""

    if finish is not None and finish <= CUTOFF and identifier not in IN_PROGRESS:
        actual_finish = ACTUAL_FINISH.get(identifier, finish)
        factor = COST_FACTOR.get(identifier, 1.0)
        return {
            "avance_pct": 100,
            "inicio_real": start,
            "fin_real": actual_finish,
            "costo_real": round(planned_cost * factor) if kind == "SUBACTIVIDAD" else "",
        }
    if identifier in IN_PROGRESS:
        progress = IN_PROGRESS[identifier]
        factor = COST_FACTOR.get(identifier, 1.0)
        return {
            "avance_pct": progress,
            "inicio_real": start,
            "fin_real": "",
            "costo_real": round(planned_cost * progress / 100 * factor),
        }
    return {"avance_pct": 0, "inicio_real": "", "fin_real": "", "costo_real": ""}


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


def _build_resources() -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    resources: list[dict[str, Any]] = []
    role_ids: dict[str, list[str]] = {}
    for role, count in ROLE_HEADCOUNT.items():
        ids: list[str] = []
        for unit in range(1, count + 1):
            identifier = f"{ROLE_PREFIX[role]}{unit}"
            ids.append(identifier)
            resources.append(
                {
                    "recurso_id": identifier,
                    "nombre": f"{role} {unit}" if count > 1 else role,
                    "tipo": "HUMANO",
                    "rol": role,
                    "tarifa": ROLE_RATES[role],
                    "unidad": "hora",
                    "capacidad_h_dia": 8,
                }
            )
        role_ids[role] = ids
    for identifier, name, kind, unit, _quantity, unit_cost, _activities in NON_LABOR:
        resources.append(
            {
                "recurso_id": identifier,
                "nombre": name,
                "tipo": kind,
                "rol": {"EQUIPAMIENTO": "Equipamiento", "INFRAESTRUCTURA_LICENCIA": "Infraestructura y licencias", "SERVICIO_EXTERNO": "Servicio externo"}[kind],
                "tarifa": unit_cost,
                "unidad": unit,
                "capacidad_h_dia": "",
            }
        )
    return resources, role_ids


def _build_assignments(planning: dict[str, dict[str, Any]], role_ids: dict[str, list[str]]) -> list[dict[str, Any]]:
    assignments: list[dict[str, Any]] = []
    load: dict[str, float] = defaultdict(float)
    for task_id in sorted((key for key in planning if key.startswith("A")), key=_leaf_sort):
        row = planning[task_id]
        roles = _roles(row.get("Recurso / Rol"))
        if not roles:
            continue
        people = max(len(roles), _as_int(row.get("N° recursos")) or len(roles))
        effort = float(_as_number(row.get("Esfuerzo (hp)")) or 0)
        h_day = _as_number(row.get("Disponibilidad (h/día)")) or 8
        base, extra = divmod(people, len(roles))
        for index, role in enumerate(roles):
            available = role_ids.get(role, [])
            wanted = min(len(available), max(1, base + (1 if index < extra else 0)))
            chosen = sorted(available, key=lambda item: (load[item], item))[:wanted]
            role_hours = effort / len(roles)
            for resource_id in chosen:
                hours = round(role_hours / len(chosen), 2)
                load[resource_id] += hours
                assignments.append(
                    {
                        "tarea_id": task_id,
                        "recurso_id": resource_id,
                        "horas_planificadas": hours,
                        "cantidad": "",
                        "h_dia": h_day,
                        "tarifa_override": "",
                    }
                )
    for identifier, _name, _kind, _unit, quantity, _unit_cost, activities in NON_LABOR:
        cents = round(quantity * 100)
        base_share, remainder = divmod(cents, len(activities))
        for index, task_id in enumerate(activities):
            share = (base_share + (1 if index < remainder else 0)) / 100
            assignments.append(
                {
                    "tarea_id": task_id,
                    "recurso_id": identifier,
                    "horas_planificadas": "",
                    "cantidad": share,
                    "h_dia": "",
                    "tarifa_override": "",
                }
            )
    return assignments


def _task_planned_costs(assignments: list[dict[str, Any]], resources: list[dict[str, Any]]) -> dict[str, float]:
    rates = {row["recurso_id"]: (row["tipo"], float(row["tarifa"])) for row in resources}
    totals: dict[str, float] = defaultdict(float)
    for row in assignments:
        kind, rate = rates[row["recurso_id"]]
        amount = float(row["horas_planificadas"] or 0) if kind == "HUMANO" else float(row["cantidad"] or 0)
        totals[row["tarea_id"]] += amount * rate
    return totals


def _build_milestone_support(schedule: dict[str, dict[str, Any]], activities: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    criteria: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    for identifier in sorted((key for key in schedule if key.startswith("H")), key=_leaf_sort):
        row = schedule[identifier]
        source = activities.get(identifier, {})
        responsible = _text(source.get("Responsable / Rol")).replace("Hito (responsable: ", "").rstrip(")") or "Jefe de Proyecto"
        criteria.append(
            {
                "hito_id": identifier,
                "criterio_id": f"CR-{identifier}-01",
                "descripcion": _text(source.get("¿Terminada cuando...?")) or "Entregable aprobado",
                "forma_de_verificacion": "Revisión del acta firmada en comité",
                "responsable": responsible,
            }
        )
        for index, predecessor in enumerate(_predecessor_ids(row), start=2):
            links.append({"hito_id": identifier, "tarea_id": predecessor})
            task = activities.get(predecessor)
            if task is None or predecessor.startswith("H"):
                continue
            criteria.append(
                {
                    "hito_id": identifier,
                    "criterio_id": f"CR-{identifier}-{index:02d}",
                    "descripcion": f"{predecessor}: {_text(task.get('¿Terminada cuando...?')) or _text(task.get('Resultado verificable'))}",
                    "forma_de_verificacion": f"Inspección del resultado verificable: {_text(task.get('Resultado verificable'))}",
                    "responsable": _text(task.get("Responsable / Rol")) or responsible,
                }
            )
    return criteria, links


def _project_rows() -> list[dict[str, str]]:
    values = {
        "codigo": "HORIZONTE-CONECTA",
        "nombre": "Horizonte Conecta",
        "cliente": "Constructora Horizonte",
        "responsable": "Kevin Henríquez Rojas",
        "fecha_inicio": "2026-10-05",
        "fecha_comprometida": "2027-08-04",
        "presupuesto": "234109000",
        "contingencia_pct": "10",
        "horas_por_dia": "8",
        "dias_laborales": "L-V",
        "fecha_corte": CUTOFF.isoformat(),
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
    suffix = "" if dependency_type == "FS" else dependency_type
    return ";".join(f"{item}{suffix}" for item in _predecessor_ids(row))


def _predecessor_ids(row: dict[str, Any]) -> list[str]:
    value = _text(row.get("Predecesora(s)"))
    if not value or value in {"—", "-", "–"}:
        return []
    return [item.strip() for item in re.split(r"[,;]", value) if item.strip()]


def _roles(value: Any) -> list[str]:
    return [item.strip() for item in _text(value).split("+") if item.strip() and item.strip().lower() != "hito"]


def _package_sort(value: str) -> tuple[int, ...]:
    return tuple(int(item) if item.isdigit() else 999 for item in value.split("."))


def _leaf_sort(value: str) -> tuple[int, int]:
    digits = re.sub(r"\D", "", value)
    return (0 if value.startswith("A") else 1, int(digits) if digits else math.inf)  # type: ignore[return-value]


def _stage_id(package: str) -> str:
    return "E" + package.removeprefix("1.")


def _activity_id(package: str) -> str:
    return "AC" + package.removeprefix("1.")


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
