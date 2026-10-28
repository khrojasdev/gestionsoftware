"""Construye de forma determinista el Seed B («Caso de prueba mínimo»).

Cubre exactamente la evidencia mínima de la rúbrica: 4 etapas, 12 actividades,
20 subactividades, los 4 tipos de dependencia (FS, SS, FF, SF), 5 profesionales,
4 tipos de recursos, 6 hitos con criterios, 5 solicitudes de cambio, 8 KPI de
proyecto e hitos, 12 KPI de gestión del cambio y 2 tableros.

Las fechas se calculan con el mismo motor de programación de la aplicación, por
lo que el archivo importado reproduce exactamente su propio cronograma.

Uso (desde la raíz del repositorio):  python seeds/build_seed_b.py
Solo escribe dentro de ``seeds/``; nunca lee ni modifica ``insumos/``.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.domain.models import Task  # noqa: E402
from app.services.calendar import BusinessCalendar, chilean_holidays  # noqa: E402
from app.services.scheduler import Scheduler, parse_predecessors  # noqa: E402
from trazo_importer.converter import CHANGE_KPIS, PROJECT_KPIS, change_stage_rows, dashboard_rows, kpi_rows  # noqa: E402
from trazo_importer.spreadsheet import write_csv_bundle, write_xlsx  # noqa: E402

SEEDS = ROOT / "seeds"
CSV_OUTPUT = SEEDS / "seed_b_caso_prueba_minimo"
JSON_OUTPUT = SEEDS / "Seed_B_Caso_Prueba_Minimo.json"
XLSX_OUTPUT = SEEDS / "Seed_B_Caso_Prueba_Minimo.xlsx"

START = date(2026, 9, 7)
CUTOFF = date(2026, 10, 30)
HOLIDAYS = sorted(day for year in (2026, 2027) for day in chilean_holidays(year) if date(2026, 9, 1) <= day <= date(2027, 3, 31))

STAGES = [
    ("E1", "Inicio y requisitos"),
    ("E2", "Diseño y construcción"),
    ("E3", "Integración y pruebas"),
    ("E4", "Despliegue y cierre"),
]
ACTIVITIES = [
    ("AC1.1", "E1", "Inicio del proyecto"),
    ("AC1.2", "E1", "Levantamiento en obra"),
    ("AC1.3", "E1", "Alcance y backlog"),
    ("AC2.1", "E2", "Diseño de la solución"),
    ("AC2.2", "E2", "Construcción backend"),
    ("AC2.3", "E2", "Construcción app móvil"),
    ("AC3.1", "E3", "Integraciones"),
    ("AC3.2", "E3", "Pruebas técnicas"),
    ("AC3.3", "E3", "Aceptación usuaria"),
    ("AC4.1", "E4", "Preparación de usuarios"),
    ("AC4.2", "E4", "Puesta en marcha"),
    ("AC4.3", "E4", "Cierre del proyecto"),
]
# id, parent, name, duration, predecessors, resources [(id, h/día)]
TASKS: list[tuple[str, str, str, int, str, list[tuple[str, float]]]] = [
    ("A01", "AC1.1", "Realizar kick-off y plan de trabajo", 3, "", [("P1", 8), ("P2", 4)]),
    ("A02", "AC1.2", "Entrevistar a jefes de obra e inspectores", 5, "A01", [("P2", 8)]),
    ("A03", "AC1.2", "Redactar historias de usuario", 6, "A02SS+2", [("P2", 4), ("P1", 2)]),
    ("A04", "AC1.3", "Priorizar backlog con el cliente", 2, "A03", [("P1", 4), ("P2", 4)]),
    ("A05", "AC2.1", "Diseñar prototipo UX de inspección", 8, "H01", [("P4", 6), ("P2", 2)]),
    ("A06", "AC2.1", "Diseñar arquitectura y modelo de datos", 6, "A05SS+1", [("P3", 6)]),
    ("A07", "AC2.2", "Construir API de inspecciones", 10, "H02", [("P3", 8)]),
    ("A08", "AC2.2", "Construir reportes y exportación", 6, "A07", [("P3", 8)]),
    ("A09", "AC2.3", "Construir app móvil offline", 12, "A07SS+2", [("P4", 8)]),
    ("A10", "AC2.3", "Integrar captura de fotos georreferenciadas", 5, "A09FF", [("P4", 4)]),
    ("A11", "AC3.1", "Integrar inicio de sesión corporativo (SSO)", 4, "H03", [("P3", 8)]),
    ("A12", "AC3.1", "Integrar ERP en modo lectura", 6, "A11", [("P3", 8)]),
    ("A13", "AC3.2", "Ejecutar pruebas de sistema", 6, "A12", [("P5", 8), ("P3", 4)]),
    ("A14", "AC3.2", "Ejecutar prueba de seguridad externa", 3, "A13SS+3", [("P5", 4)]),
    ("A15", "AC3.3", "Realizar UAT con jefes de obra", 4, "A13;A14", [("P5", 6), ("P2", 6)]),
    ("A16", "AC4.1", "Capacitar a usuarios de obra", 4, "A15SS+1;A17SF", [("P2", 6)]),
    ("A17", "AC4.2", "Desplegar en producción", 1, "H04", [("P3", 8)]),
    ("A18", "AC4.2", "Acompañar operación asistida", 10, "A17", [("P2", 4), ("P4", 4)]),
    ("A19", "AC4.3", "Evaluar resultados del piloto", 3, "A18", [("P1", 6), ("P2", 4)]),
    ("A20", "AC4.3", "Elaborar informe y acta de cierre", 2, "A19", [("P1", 8)]),
]
MILESTONES: list[tuple[str, str, str, str, list[str]]] = [
    ("H01", "AC1.3", "Alcance aprobado", "A04", ["Acta de alcance firmada por el cliente", "Backlog priorizado publicado"]),
    ("H02", "AC2.1", "Diseño de solución aprobado", "A05;A06", ["Prototipo validado con 3 jefes de obra", "Arquitectura aprobada por TI"]),
    ("H03", "AC2.3", "Release candidata lista", "A08;A10", ["API y app desplegadas en QA", "Reportes exportan a PDF"]),
    ("H04", "AC3.3", "UAT aprobada", "A15", ["Acta UAT firmada", "0 defectos críticos abiertos"]),
    ("H05", "AC4.2", "Piloto en operación", "A17", ["App en producción en la obra piloto"]),
    ("H06", "AC4.3", "Cierre formal del proyecto", "A20", ["Acta de cierre firmada por el patrocinador"]),
]
PROFESSIONALS = [
    ("P1", "Kevin Henríquez", "Jefe de Proyecto", 30000),
    ("P2", "María Soto", "Analista Funcional / de Negocio", 22000),
    ("P3", "Diego López", "Desarrollador Backend", 24000),
    ("P4", "Christian Pérez", "Desarrollador Frontend/Móvil", 24000),
    ("P5", "Pedro Rivas", "Analista QA", 18500),
]
NON_HUMAN = [
    ("R-EQ1", "Tablets rugerizadas", "EQUIPAMIENTO", "Equipamiento", 480000, "unidad", [("A18", 4)]),
    ("R-IN1", "Infraestructura cloud QA y producción", "INFRAESTRUCTURA_LICENCIA", "Infraestructura y licencias", 850000, "mes", [("A07", 2), ("A17", 2)]),
    ("R-SE1", "Prueba de seguridad externa", "SERVICIO_EXTERNO", "Servicio externo", 2400000, "servicio", [("A14", 1)]),
]
PROGRESS = {"A09": 70, "A10": 40, "H03": 0}
LATE_FINISH = {"A05": date(2026, 9, 30)}
COST_FACTOR = {"A02": 1.1, "A05": 1.15, "A06": 0.95}
CHANGES = [
    ("CB-01", "Agregar firma digital del inspector", "ALCANCE", "MEDIA", "ABIERTA", "Registro", "Jefe de obra Viña del Mar"),
    ("CB-02", "Extender pruebas de sistema en 3 días", "PLAZO", "ALTA", "ABIERTA", "Análisis de impacto", "Analista QA"),
    ("CB-03", "Comprar 2 tablets adicionales", "COSTO", "BAJA", "ABIERTA", "Revisión del comité", "Administración de obra"),
    ("CB-04", "Sumar apoyo QA en UAT", "RECURSOS", "MEDIA", "APROBADA", "Planificación del cambio", "Jefe de Proyecto"),
    ("CB-05", "Exportar reportes a Excel editable", "ALCANCE", "BAJA", "RECHAZADA", "Revisión del comité", "Oficina técnica"),
]


def schedule() -> dict[str, Task]:
    calendar = BusinessCalendar(HOLIDAYS)
    tasks = [
        Task(task_id, kind="SUBACTIVIDAD", duration_days=duration, predecessors=parse_predecessors(predecessors.replace(";", ";")))
        for task_id, _, _, duration, predecessors, _ in TASKS
    ]
    tasks += [Task(milestone_id, kind="HITO", duration_days=0, predecessors=parse_predecessors(predecessors)) for milestone_id, _, _, predecessors, _ in MILESTONES]
    return Scheduler(calendar).schedule(tasks, project_start=START).tasks


def build() -> dict[str, list[dict[str, Any]]]:
    calendar = BusinessCalendar(HOLIDAYS)
    planned = schedule()
    rates = {item[0]: item[3] for item in PROFESSIONALS}
    task_cost: dict[str, float] = {}
    assignments: list[dict[str, Any]] = []
    for task_id, _, _, duration, _, people in TASKS:
        cost = 0.0
        for resource_id, h_day in people:
            hours = duration * h_day
            cost += hours * rates[resource_id]
            assignments.append({"tarea_id": task_id, "recurso_id": resource_id, "horas_planificadas": hours, "cantidad": "", "h_dia": h_day, "tarifa_override": ""})
        task_cost[task_id] = cost
    for resource_id, _, _, _, unit_cost, _, uses in NON_HUMAN:
        for task_id, quantity in uses:
            assignments.append({"tarea_id": task_id, "recurso_id": resource_id, "horas_planificadas": "", "cantidad": quantity, "h_dia": "", "tarifa_override": ""})
            task_cost[task_id] = task_cost.get(task_id, 0) + quantity * unit_cost

    gantt: list[dict[str, Any]] = []
    for stage_id, name in STAGES:
        gantt.append(_row(stage_id, "ETAPA", name, ""))
        for activity_id, parent, activity_name in ACTIVITIES:
            if parent != stage_id:
                continue
            gantt.append(_row(activity_id, "ACTIVIDAD", activity_name, stage_id))
            leaves = [(task_id, "SUBACTIVIDAD", name_, predecessors) for task_id, act, name_, _, predecessors, _ in TASKS if act == activity_id]
            leaves += [(mid, "HITO", name_, predecessors) for mid, act, name_, predecessors, _ in MILESTONES if act == activity_id]
            leaves.sort(key=lambda item: (planned[item[0]].start, item[1] == "HITO", item[0]))
            for leaf_id, kind, leaf_name, predecessors in leaves:
                task = planned[leaf_id]
                values: dict[str, Any] = {
                    "inicio_plan": task.start,
                    "fin_plan": task.finish,
                    "duracion_dias": task.duration_days,
                    "predecesoras": _explicit(predecessors),
                }
                values.update(_progress(leaf_id, kind, task, task_cost.get(leaf_id, 0.0), calendar))
                gantt.append(_row(leaf_id, kind, leaf_name, activity_id, **values))

    resources = [
        {"recurso_id": rid, "nombre": name, "tipo": "HUMANO", "rol": role, "tarifa": rate, "unidad": "hora", "capacidad_h_dia": 8}
        for rid, name, role, rate in PROFESSIONALS
    ] + [
        {"recurso_id": rid, "nombre": name, "tipo": kind, "rol": role, "tarifa": cost, "unidad": unit, "capacidad_h_dia": ""}
        for rid, name, kind, role, cost, unit, _ in NON_HUMAN
    ]
    criteria = []
    links = []
    for milestone_id, _, _, predecessors, descriptions in MILESTONES:
        for index, description in enumerate(descriptions, start=1):
            criteria.append(
                {
                    "hito_id": milestone_id,
                    "criterio_id": f"CR-{milestone_id}-{index:02d}",
                    "descripcion": description,
                    "forma_de_verificacion": "Revisión del entregable y del acta en comité",
                    "responsable": "Kevin Henríquez",
                }
            )
        for predecessor in predecessors.split(";"):
            links.append({"hito_id": milestone_id, "tarea_id": predecessor})
    total = sum(task_cost.values())
    project = {
        "codigo": "CASO-PRUEBA",
        "nombre": "Caso de prueba mínimo · App de inspecciones",
        "cliente": "Constructora Horizonte",
        "responsable": "Kevin Henríquez",
        "fecha_inicio": START.isoformat(),
        "fecha_comprometida": "2027-01-29",
        "presupuesto": str(round(total * 1.1)),
        "contingencia_pct": "10",
        "horas_por_dia": "8",
        "dias_laborales": "L-V",
        "fecha_corte": CUTOFF.isoformat(),
    }
    return {
        "Proyecto": [{"clave": key, "valor": value} for key, value in project.items()],
        "Calendario": [{"fecha": day, "tipo": "FERIADO", "recurso_id": "", "descripcion": "Feriado nacional"} for day in HOLIDAYS],
        "Gantt": gantt,
        "Recursos": resources,
        "Asignaciones": assignments,
        "Criterios": criteria,
        "Hitos_Tareas": links,
        "Etapas_Cambio": change_stage_rows(),
        "Cambios": [
            {"id": code, "titulo": title, "tipo": kind, "prioridad": priority, "estado": status, "etapa_actual": stage, "solicitante": requester, "justificacion": ""}
            for code, title, kind, priority, status, stage, requester in CHANGES
        ],
        "KPI_Proyecto_Hitos": kpi_rows(PROJECT_KPIS),
        "KPI_Cambio": kpi_rows(CHANGE_KPIS),
        "Tableros": dashboard_rows(),
    }


def _explicit(predecessors: str) -> str:
    """Write every dependency with its explicit type (A01 → A01FS)."""

    parts = []
    for token in filter(None, (item.strip() for item in predecessors.split(";"))):
        dependency = parse_predecessors(token)[0]
        lag = f"{dependency.lag_days:+d}" if dependency.lag_days else ""
        parts.append(f"{dependency.predecessor_id}{dependency.dependency_type}{lag}")
    return ";".join(parts)


def _progress(task_id: str, kind: str, task: Task, cost: float, calendar: BusinessCalendar) -> dict[str, Any]:
    if task.finish <= CUTOFF and task_id not in PROGRESS:
        finish = LATE_FINISH.get(task_id, task.finish)
        return {
            "avance_pct": 100,
            "inicio_real": task.start,
            "fin_real": finish,
            "costo_real": round(cost * COST_FACTOR.get(task_id, 1.0)) if kind == "SUBACTIVIDAD" else "",
        }
    if task_id in PROGRESS:
        value = PROGRESS[task_id]
        if value == 0:
            return {"avance_pct": 0, "inicio_real": "", "fin_real": "", "costo_real": ""}
        return {"avance_pct": value, "inicio_real": task.start, "fin_real": "", "costo_real": round(cost * value / 100)}
    return {"avance_pct": 0, "inicio_real": "", "fin_real": "", "costo_real": ""}


def _row(identifier: str, kind: str, name: str, parent: str, **values: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": identifier, "tipo": kind, "nombre": name, "padre_id": parent, "inicio_plan": "", "fin_plan": "",
        "duracion_dias": "", "predecesoras": "", "avance_pct": "", "inicio_real": "", "fin_real": "", "costo_real": "",
    }
    row.update(values)
    return row


def main() -> int:
    sheets = build()
    write_xlsx(sheets, XLSX_OUTPUT)
    write_csv_bundle(sheets, CSV_OUTPUT)
    JSON_OUTPUT.write_text(json.dumps({"metadata": {"seed": "B", "cutoff": CUTOFF.isoformat()}, **sheets}, default=str, ensure_ascii=False, indent=2), encoding="utf-8")
    counts = {kind: sum(1 for row in sheets["Gantt"] if row["tipo"] == kind) for kind in ("ETAPA", "ACTIVIDAD", "SUBACTIVIDAD", "HITO")}
    print(f"Seed B generado: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
