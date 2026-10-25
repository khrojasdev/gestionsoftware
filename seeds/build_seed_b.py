"""Construye de forma determinista el Seed B y sus formatos de importación.

El script solo escribe dentro de ``seeds/``.  No lee ni modifica ``insumos/``.
Se conserva junto al seed para que resetear la demo sea reproducible.
"""

from __future__ import annotations

import json
import csv
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from trazo_importer.spreadsheet import write_csv_bundle, write_xlsx  # noqa: E402


SEEDS = ROOT / "seeds"
CSV_OUTPUT = SEEDS / "seed_b_caso_prueba_minimo"
JSON_OUTPUT = SEEDS / "Seed_B_Caso_Prueba_Minimo.json"
XLSX_OUTPUT = SEEDS / "Seed_B_Caso_Prueba_Minimo.xlsx"
HOLIDAY = date(2026, 5, 1)


def next_business_day(value: date) -> date:
    """Return the next Monday-Friday date, excluding the seed holiday."""

    candidate = value + timedelta(days=1)
    while candidate.weekday() >= 5 or candidate == HOLIDAY:
        candidate += timedelta(days=1)
    return candidate


def add_business_days(start: date, duration: int) -> date:
    """Return the inclusive finish for a business-day duration."""

    current = start
    remaining = duration - 1
    while remaining:
        current = next_business_day(current)
        remaining -= 1
    return current


def project_rows() -> list[dict[str, str]]:
    """Return the project metadata required by the canonical importer."""

    values = {
        "codigo": "SEED-B-MINIMO",
        "nombre": "Caso de prueba mínimo",
        "cliente": "Constructora Horizonte",
        "responsable": "Jefe de Proyecto",
        "fecha_inicio": "2026-01-05",
        "fecha_comprometida": "2026-06-30",
        "presupuesto": "45000000",
        "contingencia_pct": "10",
        "horas_por_dia": "8",
        "dias_laborales": "L-V",
        "fecha_corte": "2026-03-31",
    }
    return [{"clave": key, "valor": value} for key, value in values.items()]


def gantt_rows() -> list[dict[str, Any]]:
    """Create exactly 4 stages, 12 activities, 20 tasks and 6 milestones."""

    stages = [
        ("E01", "Inicio y definición"),
        ("E02", "Diseño y construcción"),
        ("E03", "Integración y pruebas"),
        ("E04", "Despliegue y cierre"),
    ]
    activities = [
        ("AC11", "E01", "Alineamiento inicial"),
        ("AC12", "E01", "Requisitos"),
        ("AC13", "E01", "Plan de trabajo"),
        ("AC21", "E02", "Diseño funcional"),
        ("AC22", "E02", "Construcción núcleo"),
        ("AC23", "E02", "Construcción móvil"),
        ("AC31", "E03", "Integraciones"),
        ("AC32", "E03", "Pruebas técnicas"),
        ("AC33", "E03", "Aceptación usuaria"),
        ("AC41", "E04", "Preparación productiva"),
        ("AC42", "E04", "Adopción"),
        ("AC43", "E04", "Cierre"),
    ]
    task_parents = [
        "AC11", "AC11", "AC12", "AC12", "AC13",
        "AC21", "AC21", "AC22", "AC22", "AC23",
        "AC31", "AC31", "AC32", "AC32", "AC33",
        "AC41", "AC41", "AC42", "AC42", "AC43",
    ]
    dependency_by_task = {
        "A02": "A01FS", "A03": "A02SS", "A04": "A03FF", "A05": "A04SF",
        "A06": "A05FS", "A07": "A06FS", "A08": "A07SS", "A09": "A08FS",
        "A10": "A09FF", "A11": "A10SF", "A12": "A11FS", "A13": "A12FS",
        "A14": "A13SS", "A15": "A14FS", "A16": "A15FF", "A17": "A16FS",
        "A18": "A17SF", "A19": "A18FS", "A20": "A19FS",
    }
    rows: list[dict[str, Any]] = []
    for identifier, name in stages:
        rows.append(_gantt_row(identifier, "ETAPA", name, ""))
    for identifier, parent, name in activities:
        rows.append(_gantt_row(identifier, "ACTIVIDAD", name, parent))

    current = date(2026, 1, 5)
    task_finish: dict[str, date] = {}
    for index, parent in enumerate(task_parents, 1):
        identifier = f"A{index:02d}"
        duration = 3 + ((index - 1) % 3)
        finish = add_business_days(current, duration)
        rows.append(
            _gantt_row(
                identifier,
                "SUBACTIVIDAD",
                f"Trabajo demostrable {index:02d}",
                parent,
                inicio_plan=current,
                fin_plan=finish,
                duracion_dias=duration,
                predecesoras=dependency_by_task.get(identifier, ""),
                avance_pct=0,
            )
        )
        task_finish[identifier] = finish
        current = next_business_day(finish)

    milestone_links = {
        "H01": ("AC11", "A02", "Acta de inicio aprobada"),
        "H02": ("AC12", "A04", "Requisitos validados"),
        "H03": ("AC21", "A07", "Diseño aprobado"),
        "H04": ("AC31", "A12", "Integración disponible"),
        "H05": ("AC33", "A15", "UAT aprobada"),
        "H06": ("AC43", "A20", "Cierre formal aprobado"),
    }
    for identifier, (parent, predecessor, name) in milestone_links.items():
        milestone_date = task_finish[predecessor]
        rows.append(
            _gantt_row(
                identifier,
                "HITO",
                name,
                parent,
                inicio_plan=milestone_date,
                fin_plan=milestone_date,
                duracion_dias=0,
                predecesoras=f"{predecessor}FS",
                avance_pct=0,
            )
        )
    return rows


def _gantt_row(identifier: str, kind: str, name: str, parent: str, **values: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": identifier,
        "tipo": kind,
        "nombre": name,
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


def resources() -> list[dict[str, Any]]:
    """Return five professionals plus one resource of each non-human type."""

    return [
        {"recurso_id": "R001", "nombre": "Ana Analista", "tipo": "HUMANO", "rol": "Analista Funcional", "tarifa": 22000, "unidad": "hora", "capacidad_h_dia": 8},
        {"recurso_id": "R002", "nombre": "Bruno Backend", "tipo": "HUMANO", "rol": "Desarrollador Backend", "tarifa": 24000, "unidad": "hora", "capacidad_h_dia": 8},
        {"recurso_id": "R003", "nombre": "Carla Frontend", "tipo": "HUMANO", "rol": "Desarrollador Frontend/Móvil", "tarifa": 24000, "unidad": "hora", "capacidad_h_dia": 8},
        {"recurso_id": "R004", "nombre": "Diego QA", "tipo": "HUMANO", "rol": "Analista QA", "tarifa": 18500, "unidad": "hora", "capacidad_h_dia": 8},
        {"recurso_id": "R005", "nombre": "Elena Proyecto", "tipo": "HUMANO", "rol": "Jefe de Proyecto", "tarifa": 30000, "unidad": "hora", "capacidad_h_dia": 8},
        {"recurso_id": "R006", "nombre": "Kit tablets de obra", "tipo": "EQUIPAMIENTO", "rol": "Dispositivo", "tarifa": 350000, "unidad": "unidad", "capacidad_h_dia": ""},
        {"recurso_id": "R007", "nombre": "Nube de prueba", "tipo": "INFRAESTRUCTURA_LICENCIA", "rol": "Cloud", "tarifa": 1200000, "unidad": "mes", "capacidad_h_dia": ""},
        {"recurso_id": "R008", "nombre": "Servicio API externo", "tipo": "SERVICIO_EXTERNO", "rol": "Proveedor", "tarifa": 3000000, "unidad": "servicio", "capacidad_h_dia": ""},
    ]


def assignments() -> list[dict[str, Any]]:
    """Assign every subactivity and exercise all four resource types."""

    human_ids = ["R001", "R002", "R003", "R004", "R005"]
    rows: list[dict[str, Any]] = []
    for index in range(1, 21):
        resource_id = human_ids[(index - 1) % len(human_ids)]
        rows.append(
            {
                "tarea_id": f"A{index:02d}",
                "recurso_id": resource_id,
                "horas_planificadas": 24 + (index % 3) * 8,
                "cantidad": "",
                "h_dia": 8,
                "tarifa_override": "",
            }
        )
    rows.extend(
        [
            {"tarea_id": "A05", "recurso_id": "R006", "horas_planificadas": "", "cantidad": 2, "h_dia": "", "tarifa_override": ""},
            {"tarea_id": "A10", "recurso_id": "R007", "horas_planificadas": "", "cantidad": 1, "h_dia": "", "tarifa_override": ""},
            {"tarea_id": "A15", "recurso_id": "R008", "horas_planificadas": "", "cantidad": 1, "h_dia": "", "tarifa_override": ""},
        ]
    )
    return rows


def criteria() -> list[dict[str, str]]:
    """Return one acceptance criterion for each of the six milestones."""

    return [
        {"hito_id": f"H{index:02d}", "criterio_id": f"CR-H{index:02d}-01", "descripcion": f"Evidencia aprobada del hito {index:02d}", "forma_de_verificacion": "Acta firmada y revisión del entregable", "responsable": "Jefe de Proyecto"}
        for index in range(1, 7)
    ]


def milestone_tasks() -> list[dict[str, str]]:
    """Link each milestone to its completing subactivity."""

    return [
        {"hito_id": f"H{index:02d}", "tarea_id": f"A{task:02d}"}
        for index, task in enumerate((2, 4, 7, 12, 15, 20), 1)
    ]


def extras() -> dict[str, Any]:
    """Return F9 data not represented by the canonical import sheets."""

    change_stages = [
        {"id": f"CS{index:02d}", "nombre": name, "secuencia": index, "sla_horas": 24 * index}
        for index, name in enumerate(("Registro", "Revisión inicial", "Clasificación", "Análisis de impacto", "Revisión del comité", "Decisión", "Planificación", "Implementación", "Verificación", "Cierre"), 1)
    ]
    changes = [
        {"id": "CR-001", "titulo": "Ajustar duración de integración", "tipo": "PLAZO", "prioridad": "MEDIA", "estado": "ABIERTA", "etapa_actual": "Registro", "delta_dias": 2, "delta_costo": 480000},
        {"id": "CR-002", "titulo": "Agregar tablet para piloto", "tipo": "RECURSOS", "prioridad": "ALTA", "estado": "ABIERTA", "etapa_actual": "Análisis de impacto", "delta_dias": 0, "delta_costo": 350000},
        {"id": "CR-003", "titulo": "Incluir reporte ejecutivo", "tipo": "ALCANCE", "prioridad": "BAJA", "estado": "ABIERTA", "etapa_actual": "Revisión del comité", "delta_dias": 4, "delta_costo": 960000},
        {"id": "CR-004", "titulo": "Cambiar proveedor API", "tipo": "COSTO", "prioridad": "ALTA", "estado": "ABIERTA", "etapa_actual": "Implementación", "delta_dias": 1, "delta_costo": 1200000},
        {"id": "CR-005", "titulo": "Cerrar capacitación piloto", "tipo": "ALCANCE", "prioridad": "MEDIA", "estado": "APROBADA", "etapa_actual": "Cierre", "delta_dias": 0, "delta_costo": 220000},
    ]
    project_kpis = [
        ("SPI", "Índice de desempeño de plazo", "EV / PV", "PROYECTO"),
        ("CPI", "Índice de desempeño de costo", "EV / AC", "PROYECTO"),
        ("SV", "Variación de plazo", "EV - PV", "PROYECTO"),
        ("CV", "Variación de costo", "EV - AC", "PROYECTO"),
        ("ADVANCE_GAP", "Desviación de avance físico", "avance_real - avance_plan", "PROYECTO"),
        ("LATE_TASKS", "Actividades atrasadas", "count(actividades_atrasadas) / count(actividades)", "PROYECTO"),
        ("MILESTONE_ON_TIME", "Hitos cumplidos a tiempo", "count(hitos_a_tiempo) / count(hitos)", "HITO"),
        ("CLOSE_VARIANCE", "Desviación del hito de cierre", "fecha_cierre_real - fecha_cierre_base", "HITO"),
    ]
    change_kpi_names = (
        "solicitudes registradas", "tasa de aprobación", "tasa de rechazo", "tiempo medio de ciclo",
        "tiempo medio de evaluación de impacto", "impacto acumulado en costo", "impacto acumulado en plazo",
        "% con evidencia completa", "solicitudes fuera de SLA", "consumo de contingencia",
        "índice de adopción", "cobertura de capacitación",
    )
    return {
        "Etapas_Cambio": change_stages,
        "Cambios": changes,
        "KPI_Proyecto_Hitos": [
            {"codigo": code, "nombre": name, "formula": formula, "ambito": scope, "meta": 1}
            for code, name, formula, scope in project_kpis
        ],
        "KPI_Cambio": [
            {"codigo": f"CHG-{index:02d}", "nombre": name, "formula": f"valor_{index:02d}", "ambito": "PROYECTO", "meta": 1}
            for index, name in enumerate(change_kpi_names, 1)
        ],
        "Tableros": [
            {"id": "DB-PROYECTO", "nombre": "Tablero del proyecto", "tipo": "PROYECTO", "kpis": ["SPI", "CPI", "SV", "CV", "ADVANCE_GAP", "LATE_TASKS", "MILESTONE_ON_TIME", "CLOSE_VARIANCE"]},
            {"id": "DB-CAMBIOS", "nombre": "Tablero de gestión del cambio", "tipo": "CAMBIO", "kpis": [f"CHG-{index:02d}" for index in range(1, 13)]},
        ],
    }


def build() -> dict[str, Any]:
    """Build, validate shape, and write every reproducible Seed B artifact."""

    sheets: dict[str, Any] = {
        "Proyecto": project_rows(),
        "Calendario": [{"fecha": HOLIDAY, "tipo": "FERIADO", "recurso_id": "", "descripcion": "Día del Trabajo"}],
        "Gantt": gantt_rows(),
        "Recursos": resources(),
        "Asignaciones": assignments(),
        "Criterios": criteria(),
        "Hitos_Tareas": milestone_tasks(),
    }
    seed: dict[str, Any] = {
        "metadata": {
            "seed": "B",
            "nombre": "Caso de prueba mínimo",
            "version": "1.0",
            "formato_importacion": "Carta Gantt canónica",
            "reset_command": "python seeds/build_seed_b.py",
            "load_command": "python seeds/verificar_f9.py",
        },
        **sheets,
        **extras(),
    }
    supplemental = {name: seed[name] for name in ("Etapas_Cambio", "Cambios", "KPI_Proyecto_Hitos", "KPI_Cambio", "Tableros")}
    _assert_shape(seed)
    CSV_OUTPUT.mkdir(parents=True, exist_ok=True)
    write_csv_bundle(sheets, CSV_OUTPUT)
    _write_supplemental_csv(seed, "Etapas_Cambio")
    _write_supplemental_csv(seed, "Cambios")
    _write_supplemental_csv(seed, "KPI_Proyecto_Hitos")
    _write_supplemental_csv(seed, "KPI_Cambio")
    _write_supplemental_csv(seed, "Tableros")
    write_xlsx({**sheets, **supplemental}, XLSX_OUTPUT)
    JSON_OUTPUT.write_text(json.dumps(seed, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return seed


def _write_supplemental_csv(seed: dict[str, Any], name: str) -> None:
    """Write F9 entities not part of the seven-sheet import contract."""

    rows = seed[name]
    headers = list(rows[0])
    with (CSV_OUTPUT / f"{name}.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            normalized = {
                key: json.dumps(value, ensure_ascii=False) if isinstance(value, list) else value
                for key, value in row.items()
            }
            writer.writerow(normalized)


def _assert_shape(seed: dict[str, Any]) -> None:
    """Fail fast if a future edit breaks the evidence minimum."""

    kinds = {kind: sum(row["tipo"] == kind for row in seed["Gantt"]) for kind in ("ETAPA", "ACTIVIDAD", "SUBACTIVIDAD", "HITO")}
    expected = {"ETAPA": 4, "ACTIVIDAD": 12, "SUBACTIVIDAD": 20, "HITO": 6}
    if kinds != expected or len(seed["Recursos"]) != 8 or len(seed["Criterios"]) != 6 or len(seed["Cambios"]) != 5:
        raise ValueError(f"Seed B fuera de contrato: {kinds}")
    if len(seed["KPI_Proyecto_Hitos"]) != 8 or len(seed["KPI_Cambio"]) != 12 or len(seed["Tableros"]) != 2:
        raise ValueError("El Seed B no cumple los conteos de KPI/tableros")
    if set(row["tipo"] for row in seed["Recursos"]) != {"HUMANO", "EQUIPAMIENTO", "INFRAESTRUCTURA_LICENCIA", "SERVICIO_EXTERNO"}:
        raise ValueError("Faltan tipos de recurso")
    if set(row["recurso_id"] for row in seed["Recursos"] if row["tipo"] == "HUMANO") != {"R001", "R002", "R003", "R004", "R005"}:
        raise ValueError("El Seed B debe tener exactamente cinco profesionales")


if __name__ == "__main__":
    result = build()
    print(f"Seed B generado: {len(result['Gantt'])} elementos, {len(result['Recursos'])} recursos")
