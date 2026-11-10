"""Construye una Carta Gantt de demostración NUEVA y distinta del seed Horizonte.

Proyecto: «RutaViva — Plataforma de logística de última milla».
Datos nuevos (fechas, equipo, tareas, hitos, cambios) pero con la misma
estructura canónica que entiende el importador de Trazo, de modo que al
importarlo se crea un proyecto completo y navegable para la demo en vivo.

Cubre: 4 etapas, 12 actividades, 20 subactividades, los 4 tipos de dependencia
(FS, SS, FF, SF), 5 profesionales + 3 recursos no humanos, 6 hitos con criterios,
5 solicitudes de cambio, 20 KPI (8 de proyecto + 12 de cambio) y 2 tableros.

Las fechas se calculan con el mismo motor de la aplicación, así el archivo
reproduce exactamente su propio cronograma al importarse.

Uso:
    python seeds/build_demo_rutaviva.py            # escribe seeds/RutaViva_Carta_Gantt_Demo.xlsx
    python seeds/build_demo_rutaviva.py --out ruta/a/archivo.xlsx

Para crear OTRA versión distinta, copia este archivo y cambia los datos de
STAGES/ACTIVITIES/TASKS/MILESTONES/PROFESSIONALS/CHANGES y el bloque `project`
(código y nombre). La estructura y el motor se encargan del resto.
"""

from __future__ import annotations

import argparse
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
from trazo_importer.spreadsheet import write_xlsx  # noqa: E402

DEFAULT_OUT = ROOT / "seeds" / "RutaViva_Carta_Gantt_Demo.xlsx"

START = date(2026, 3, 2)   # lunes
CUTOFF = date(2026, 5, 15)
HOLIDAYS = sorted(day for year in (2026, 2027) for day in chilean_holidays(year) if date(2026, 3, 1) <= day <= date(2027, 2, 28))

STAGES = [
    ("E1", "Descubrimiento y alcance"),
    ("E2", "Diseño y desarrollo"),
    ("E3", "Integración y pruebas"),
    ("E4", "Piloto y puesta en marcha"),
]
ACTIVITIES = [
    ("AC1.1", "E1", "Arranque del proyecto"),
    ("AC1.2", "E1", "Relevamiento operativo"),
    ("AC1.3", "E1", "Definición del alcance"),
    ("AC2.1", "E2", "Diseño de la plataforma"),
    ("AC2.2", "E2", "Motor de ruteo y backend"),
    ("AC2.3", "E2", "App del conductor"),
    ("AC3.1", "E3", "Integraciones externas"),
    ("AC3.2", "E3", "Pruebas y calidad"),
    ("AC3.3", "E3", "Aceptación del cliente"),
    ("AC4.1", "E4", "Preparación del piloto"),
    ("AC4.2", "E4", "Operación asistida"),
    ("AC4.3", "E4", "Cierre del proyecto"),
]
# id, parent, name, duration, predecessors, resources [(id, h/día)]
TASKS: list[tuple[str, str, str, int, str, list[tuple[str, float]]]] = [
    ("A01", "AC1.1", "Realizar kick-off y plan de trabajo", 3, "", [("P1", 8), ("P2", 4)]),
    ("A02", "AC1.2", "Mapear el proceso de reparto actual", 5, "A01", [("P2", 8)]),
    ("A03", "AC1.2", "Analizar datos históricos de entregas", 6, "A02SS+2", [("P2", 4), ("P5", 4)]),
    ("A04", "AC1.3", "Acordar alcance y backlog con el cliente", 2, "A03;A02FF", [("P1", 4), ("P2", 4)]),
    ("A05", "AC2.1", "Diseñar experiencia de la app del conductor", 8, "H01", [("P4", 6), ("P2", 2)]),
    ("A06", "AC2.1", "Diseñar arquitectura y modelo de datos", 6, "A05SS+1", [("P3", 6)]),
    ("A07", "AC2.2", "Construir motor de optimización de rutas", 12, "H02", [("P3", 8), ("P5", 2)]),
    ("A08", "AC2.2", "Construir API de pedidos y seguimiento", 8, "A06;A07SS+3", [("P3", 8)]),
    ("A09", "AC2.3", "Construir app móvil del conductor", 12, "A05FF;A08SS+2", [("P4", 8)]),
    ("A10", "AC2.3", "Añadir navegación y prueba de entrega", 5, "A09FF", [("P4", 4)]),
    ("A11", "AC3.1", "Integrar mapas y tiempos de tránsito", 4, "H03", [("P3", 8)]),
    ("A12", "AC3.1", "Integrar ERP del cliente (pedidos)", 6, "A11", [("P3", 8)]),
    ("A13", "AC3.2", "Ejecutar pruebas de sistema", 6, "A12", [("P5", 8), ("P3", 4)]),
    ("A14", "AC3.2", "Ejecutar pruebas de carga del ruteo", 3, "A13SS+3", [("P5", 4)]),
    ("A15", "AC3.3", "Realizar UAT con despachadores", 4, "A13;A14", [("P5", 6), ("P2", 6)]),
    ("A16", "AC4.1", "Capacitar a conductores y despacho", 4, "A15SS+1;A17SF", [("P2", 6)]),
    ("A17", "AC4.2", "Desplegar en producción", 1, "H04", [("P3", 8)]),
    ("A18", "AC4.2", "Acompañar la operación del piloto", 10, "A17", [("P2", 4), ("P4", 4)]),
    ("A19", "AC4.3", "Evaluar indicadores del piloto", 3, "A18", [("P1", 6), ("P5", 4)]),
    ("A20", "AC4.3", "Elaborar informe y acta de cierre", 2, "A19", [("P1", 8)]),
]
MILESTONES: list[tuple[str, str, str, str, list[str]]] = [
    ("H01", "AC1.3", "Alcance aprobado", "A04", ["Acta de alcance firmada por el cliente", "Backlog priorizado publicado"]),
    ("H02", "AC2.1", "Diseño de solución aprobado", "A05;A06", ["Prototipo validado con 3 despachadores", "Arquitectura aprobada por TI"]),
    ("H03", "AC2.3", "Release candidata lista", "A08;A10", ["Motor de ruteo y app desplegados en QA", "Seguimiento en tiempo real operativo"]),
    ("H04", "AC3.3", "UAT aprobada", "A15", ["Acta UAT firmada", "0 defectos críticos abiertos"]),
    ("H05", "AC4.2", "Piloto en operación", "A17", ["App en producción en la ruta piloto"]),
    ("H06", "AC4.3", "Cierre formal del proyecto", "A20", ["Acta de cierre firmada por el patrocinador"]),
]
PROFESSIONALS = [
    ("P1", "Kevin Henríquez", "Jefe de Proyecto", 30000),
    ("P2", "Valentina Rojas", "Analista Funcional / de Negocio", 22000),
    ("P3", "Diego López", "Desarrollador Backend", 24000),
    ("P4", "Camila Fuentes", "Desarrolladora Frontend/Móvil", 24000),
    ("P5", "Ignacio Vera", "Analista QA / Datos", 18500),
]
NON_HUMAN = [
    ("R-EQ1", "Smartphones rugerizados para conductores", "EQUIPAMIENTO", "Equipamiento", 420000, "unidad", [("A18", 5)]),
    ("R-IN1", "Infraestructura cloud QA y producción", "INFRAESTRUCTURA_LICENCIA", "Infraestructura y licencias", 900000, "mes", [("A07", 2), ("A17", 2)]),
    ("R-SE1", "Licencia de API de mapas y tránsito", "SERVICIO_EXTERNO", "Servicio externo", 1800000, "servicio", [("A11", 1)]),
]
PROGRESS = {"A09": 65, "A10": 30, "H03": 0}
LATE_FINISH = {"A07": date(2026, 4, 20)}
COST_FACTOR = {"A02": 1.08, "A07": 1.12, "A06": 0.96}
CHANGES = [
    ("CB-01", "Agregar prueba de entrega con foto y firma", "ALCANCE", "MEDIA", "ABIERTA", "Registro", "Jefe de despacho Santiago"),
    ("CB-02", "Extender pruebas de carga en 3 días", "PLAZO", "ALTA", "ABIERTA", "Análisis de impacto", "Analista QA"),
    ("CB-03", "Comprar 3 smartphones adicionales", "COSTO", "BAJA", "ABIERTA", "Revisión del comité", "Administración de flota"),
    ("CB-04", "Sumar apoyo QA en UAT", "RECURSOS", "MEDIA", "APROBADA", "Planificación del cambio", "Jefe de Proyecto"),
    ("CB-05", "Exportar reportes de ruta a Excel editable", "ALCANCE", "BAJA", "RECHAZADA", "Revisión del comité", "Oficina de operaciones"),
]


def schedule() -> dict[str, Task]:
    calendar = BusinessCalendar(HOLIDAYS)
    tasks = [
        Task(task_id, kind="SUBACTIVIDAD", duration_days=duration, predecessors=parse_predecessors(predecessors))
        for task_id, _, _, duration, predecessors, _ in TASKS
    ]
    tasks += [Task(mid, kind="HITO", duration_days=0, predecessors=parse_predecessors(preds)) for mid, _, _, preds, _ in MILESTONES]
    return Scheduler(calendar).schedule(tasks, project_start=START).tasks


def build() -> dict[str, list[dict[str, Any]]]:
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
            leaves = [(task_id, "SUBACTIVIDAD", name_, preds) for task_id, act, name_, _, preds, _ in TASKS if act == activity_id]
            leaves += [(mid, "HITO", name_, preds) for mid, act, name_, preds, _ in MILESTONES if act == activity_id]
            leaves.sort(key=lambda item: (planned[item[0]].start, item[1] == "HITO", item[0]))
            for leaf_id, kind, leaf_name, preds in leaves:
                task = planned[leaf_id]
                values: dict[str, Any] = {
                    "inicio_plan": task.start,
                    "fin_plan": task.finish,
                    "duracion_dias": task.duration_days,
                    "predecesoras": _explicit(preds),
                }
                values.update(_progress(leaf_id, kind, task, task_cost.get(leaf_id, 0.0)))
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
    for milestone_id, _, _, preds, descriptions in MILESTONES:
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
        for predecessor in preds.split(";"):
            links.append({"hito_id": milestone_id, "tarea_id": predecessor})
    total = sum(task_cost.values())
    project = {
        "codigo": "RUTAVIVA",
        "nombre": "RutaViva · Plataforma de logística de última milla",
        "cliente": "Distribuidora Andes",
        "responsable": "Kevin Henríquez",
        "fecha_inicio": START.isoformat(),
        "fecha_comprometida": "2026-07-31",
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
    parts = []
    for token in filter(None, (item.strip() for item in predecessors.split(";"))):
        dependency = parse_predecessors(token)[0]
        lag = f"{dependency.lag_days:+d}" if dependency.lag_days else ""
        parts.append(f"{dependency.predecessor_id}{dependency.dependency_type}{lag}")
    return ";".join(parts)


def _progress(task_id: str, kind: str, task: Task, cost: float) -> dict[str, Any]:
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
    parser = argparse.ArgumentParser(description="Genera la Carta Gantt de demostración RutaViva (.xlsx).")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Ruta del .xlsx de salida (por defecto seeds/RutaViva_Carta_Gantt_Demo.xlsx).")
    args = parser.parse_args()
    sheets = build()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_xlsx(sheets, args.out)
    counts = {kind: sum(1 for row in sheets["Gantt"] if row["tipo"] == kind) for kind in ("ETAPA", "ACTIVIDAD", "SUBACTIVIDAD", "HITO")}
    print(f"RutaViva generado en {args.out}")
    print("Conteos:", json.dumps(counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
