"""Generación de la plantilla oficial de importación."""

from __future__ import annotations

from pathlib import Path

from .models import CANONICAL_COLUMNS
from .spreadsheet import write_csv_bundle, write_xlsx


def template_sheets() -> dict[str, list[dict[str, object]]]:
    """Devuelve una plantilla con instrucciones breves y un ejemplo mínimo."""

    sheets = {sheet: [] for sheet in CANONICAL_COLUMNS}
    sheets["Proyecto"] = [
        {"clave": "codigo", "valor": "EJEMPLO-001"},
        {"clave": "nombre", "valor": "Proyecto de ejemplo"},
        {"clave": "cliente", "valor": "Cliente"},
        {"clave": "responsable", "valor": "Jefe de Proyecto"},
        {"clave": "fecha_inicio", "valor": "2026-01-05"},
        {"clave": "fecha_comprometida", "valor": "2026-01-30"},
        {"clave": "presupuesto", "valor": "1000000"},
        {"clave": "contingencia_pct", "valor": "10"},
        {"clave": "horas_por_dia", "valor": "8"},
        {"clave": "dias_laborales", "valor": "L-V"},
        {"clave": "fecha_corte", "valor": "2026-01-05"},
    ]
    sheets["Calendario"] = [
        {"fecha": "2026-01-01", "tipo": "FERIADO", "recurso_id": "", "descripcion": "Año Nuevo"}
    ]
    sheets["Gantt"] = [
        {"id": "E1", "tipo": "ETAPA", "nombre": "Planificación", "padre_id": "", "inicio_plan": "", "fin_plan": "", "duracion_dias": "", "predecesoras": "", "avance_pct": "", "inicio_real": "", "fin_real": "", "costo_real": ""},
        {"id": "AC1", "tipo": "ACTIVIDAD", "nombre": "Preparación", "padre_id": "E1", "inicio_plan": "", "fin_plan": "", "duracion_dias": "", "predecesoras": "", "avance_pct": "", "inicio_real": "", "fin_real": "", "costo_real": ""},
        {"id": "A01", "tipo": "SUBACTIVIDAD", "nombre": "Definir alcance", "padre_id": "AC1", "inicio_plan": "2026-01-05", "fin_plan": "2026-01-05", "duracion_dias": "1", "predecesoras": "", "avance_pct": "0", "inicio_real": "", "fin_real": "", "costo_real": ""},
        {"id": "H01", "tipo": "HITO", "nombre": "Alcance aprobado", "padre_id": "AC1", "inicio_plan": "2026-01-06", "fin_plan": "2026-01-06", "duracion_dias": "0", "predecesoras": "A01", "avance_pct": "0", "inicio_real": "", "fin_real": "", "costo_real": ""},
    ]
    sheets["Recursos"] = [
        {"recurso_id": "R01", "nombre": "Persona ejemplo", "tipo": "HUMANO", "rol": "Analista", "tarifa": "20000", "unidad": "hora", "capacidad_h_dia": "8"}
    ]
    sheets["Asignaciones"] = [
        {"tarea_id": "A01", "recurso_id": "R01", "horas_planificadas": "8", "cantidad": "", "h_dia": "8", "tarifa_override": ""}
    ]
    sheets["Criterios"] = [
        {"hito_id": "H01", "criterio_id": "CR-H01-01", "descripcion": "Acta aprobada", "forma_de_verificacion": "Revisión del acta", "responsable": "Jefe de Proyecto"}
    ]
    sheets["Hitos_Tareas"] = [{"hito_id": "H01", "tarea_id": "A01"}]
    return sheets


def create_template(output: Path, csv_directory: Path | None = None) -> None:
    """Crea la plantilla XLSX y, opcionalmente, el paquete CSV por hoja."""

    sheets = template_sheets()
    write_xlsx(sheets, output)
    if csv_directory is not None:
        write_csv_bundle(sheets, csv_directory)
