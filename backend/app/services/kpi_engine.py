"""KPI evaluation and snapshot persistence based on ``ProjectAnalytics``."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models import Kpi, KpiValue, KpiVariable, Project
from app.services.analytics import ProjectAnalytics, json_value, kpi_status
from app.services.kpi import DEFAULT_KPI_VARIABLES, KpiFormulaError, evaluate_formula, formula_variables


def variable_codes(session: Session, project_id: Any) -> tuple[str, ...]:
    custom = session.scalars(sa.select(KpiVariable.code).where(KpiVariable.project_id == project_id)).all()
    return tuple({definition.code for definition in DEFAULT_KPI_VARIABLES} | {code.upper() for code in custom})


def evaluate(formula: str, metrics: dict[str, Any], codes: tuple[str, ...]) -> tuple[Decimal | None, dict[str, Any]]:
    """Evaluate a formula and return its value plus a human-readable breakdown."""

    used = formula_variables(formula)
    variables = {name: metrics.get(name) for name in used}
    readable = {
        name: (len(value) if isinstance(value, list) else value) for name, value in variables.items()
    }
    breakdown: dict[str, Any] = {"formula": formula, "variables": json_value(readable)}
    try:
        result = evaluate_formula(formula, metrics, codes)
    except KpiFormulaError as error:
        breakdown["error"] = str(error)
        return None, breakdown
    value = Decimal(int(result)) if isinstance(result, bool) else result
    substituted = formula
    for name in sorted(readable, key=len, reverse=True):
        number = readable[name]
        text = _fmt(number) if number is not None else "?"
        substituted = _replace_word(substituted, name, text)
    breakdown["substituted"] = substituted
    breakdown["value"] = json_value(value)
    return value, breakdown


def recalculate_kpis(
    session: Session,
    project: Project,
    at: date | None = None,
    analytics: ProjectAnalytics | None = None,
) -> list[dict[str, Any]]:
    """Compute every active KPI at ``at`` and upsert the snapshot (no commit)."""

    analytics = analytics or ProjectAnalytics(session, project)
    at = at or analytics.cutoff
    metrics = analytics.metrics(at)
    codes = variable_codes(session, project.id)
    snapshot_at = datetime.combine(at, time.min, tzinfo=UTC)
    values: list[dict[str, Any]] = []
    for kpi in session.scalars(
        sa.select(Kpi).where(Kpi.project_id == project.id, Kpi.is_active.is_(True)).order_by(Kpi.code)
    ).all():
        value, breakdown = evaluate(kpi.formula, metrics, codes)
        breakdown["status"] = kpi_status(value, kpi.green_threshold, kpi.yellow_threshold)
        existing = session.scalar(
            sa.select(KpiValue).where(
                KpiValue.kpi_id == kpi.id, KpiValue.cutoff_at == snapshot_at, KpiValue.element_id.is_(None)
            )
        )
        if existing is None:
            session.add(KpiValue(kpi_id=kpi.id, cutoff_at=snapshot_at, value=value, breakdown=breakdown))
        else:
            existing.value = value
            existing.breakdown = breakdown
            existing.calculated_at = datetime.now(UTC)
        values.append({"kpi_id": kpi.id, "code": kpi.code, "value": value, "cutoff_at": snapshot_at, "breakdown": breakdown})
    session.flush()
    return values


def _fmt(value: Any) -> str:
    if isinstance(value, Decimal | float | int):
        number = float(value)
        if abs(number) >= 1000:
            return f"{number:,.0f}".replace(",", ".")
        return f"{number:.4g}".replace(".", ",") if not float(number).is_integer() else str(int(number))
    return str(value)


def _replace_word(text: str, word: str, replacement: str) -> str:
    import re

    return re.sub(rf"\b{re.escape(word)}\b", replacement, text, flags=re.IGNORECASE)
