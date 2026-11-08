"""Traffic-light evaluation of a KPI value against its threshold rule.

Supports explicit comparators so the user controls exactly how a number turns
into a green/yellow/red risk, and produces a human-readable rule that the UI
shows next to the value ("Verde si ≥ 0,95 · Amarillo si ≥ 0,90 · Rojo si < 0,90").
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

VERDE = "VERDE"
AMARILLO = "AMARILLO"
ROJO = "ROJO"
INFO = "INFO"
SIN_DATOS = "SIN_DATOS"

# comparator -> (label, "higher is better"?)
COMPARATORS: dict[str, tuple[str, bool | None]] = {
    "GE": ("Mayor o igual (≥)", True),
    "GT": ("Mayor que (>)", True),
    "LE": ("Menor o igual (≤)", False),
    "LT": ("Menor que (<)", False),
    "RANGE": ("En rango", None),
    "INFO": ("Informativo", None),
}

_SYMBOL = {"GE": "≥", "GT": ">", "LE": "≤", "LT": "<"}


@dataclass
class Threshold:
    comparator: str = "GE"
    green: Decimal | None = None
    yellow: Decimal | None = None
    green_min: Decimal | None = None
    green_max: Decimal | None = None
    yellow_min: Decimal | None = None
    yellow_max: Decimal | None = None
    unit: str | None = None


def from_kpi(kpi: Any) -> Threshold:
    return Threshold(
        comparator=(getattr(kpi, "comparator", None) or _infer(kpi)),
        green=kpi.green_threshold,
        yellow=kpi.yellow_threshold,
        green_min=getattr(kpi, "green_min", None),
        green_max=getattr(kpi, "green_max", None),
        yellow_min=getattr(kpi, "yellow_min", None),
        yellow_max=getattr(kpi, "yellow_max", None),
        unit=getattr(kpi, "unit", None),
    )


def _infer(kpi: Any) -> str:
    """Back-compat: derive a comparator from the legacy green/yellow order."""

    green, yellow = kpi.green_threshold, kpi.yellow_threshold
    if green is None or yellow is None:
        return "INFO"
    return "GE" if Decimal(green) >= Decimal(yellow) else "LE"


def _num(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def evaluate(value: Any, threshold: Threshold) -> str:
    """Return the traffic-light status for ``value``."""

    if value is None:
        return SIN_DATOS
    val = Decimal(str(value))
    cmp = threshold.comparator
    if cmp == "INFO":
        return INFO
    if cmp == "RANGE":
        gmin, gmax = _num(threshold.green_min), _num(threshold.green_max)
        ymin, ymax = _num(threshold.yellow_min), _num(threshold.yellow_max)
        if gmin is not None and gmax is not None and gmin <= val <= gmax:
            return VERDE
        lo = ymin if ymin is not None else gmin
        hi = ymax if ymax is not None else gmax
        if lo is not None and hi is not None and lo <= val <= hi:
            return AMARILLO
        return ROJO
    green, yellow = _num(threshold.green), _num(threshold.yellow)
    if green is None or yellow is None:
        return INFO
    higher_better = cmp in ("GE", "GT")
    strict = cmp in ("GT", "LT")

    def ok(limit: Decimal) -> bool:
        if higher_better:
            return val > limit if strict else val >= limit
        return val < limit if strict else val <= limit

    if ok(green):
        return VERDE
    if ok(yellow):
        return AMARILLO
    return ROJO


def direction(threshold: Threshold) -> str:
    higher = COMPARATORS.get(threshold.comparator, ("", None))[1]
    if higher is True:
        return "MAYOR"
    if higher is False:
        return "MENOR"
    return "RANGO" if threshold.comparator == "RANGE" else "INFO"


def rule_text(threshold: Threshold) -> str:
    """Human-readable explanation of how the risk is assigned."""

    cmp = threshold.comparator
    if cmp == "INFO":
        return "Indicador informativo: se muestra el valor, sin semáforo."
    if cmp == "RANGE":
        g = f"{_fmt(threshold.green_min, threshold.unit)} y {_fmt(threshold.green_max, threshold.unit)}"
        if threshold.yellow_min is not None or threshold.yellow_max is not None:
            y = f"{_fmt(threshold.yellow_min, threshold.unit)} y {_fmt(threshold.yellow_max, threshold.unit)}"
            return f"Verde si está entre {g} · Amarillo si está entre {y} · Rojo fuera de ese rango."
        return f"Verde si está entre {g} · Rojo fuera de ese rango."
    if threshold.green is None or threshold.yellow is None:
        return "Sin umbrales definidos: el indicador es informativo."
    symbol = _SYMBOL.get(cmp, "≥")
    strict_symbol = "<" if cmp in ("GE", "GT") else ">"
    return (
        f"Verde si {symbol} {_fmt(threshold.green, threshold.unit)} · "
        f"Amarillo si {symbol} {_fmt(threshold.yellow, threshold.unit)} · "
        f"Rojo si {strict_symbol} {_fmt(threshold.yellow, threshold.unit)}."
    )


def _fmt(value: Any, unit: str | None) -> str:
    if value is None:
        return "—"
    number = float(value)
    unit = (unit or "").lower()
    if unit == "clp":
        return f"${number:,.0f}".replace(",", ".")
    body = f"{number:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".") if number % 1 else f"{number:,.0f}".replace(",", ".")
    if unit in ("%", "pp"):
        return f"{body} {unit}"
    if unit in ("días", "dias", "d"):
        return f"{body} días"
    return body


def config(threshold: Threshold) -> dict[str, Any]:
    """Serialisable view for the API/UI."""

    label = COMPARATORS.get(threshold.comparator, ("", None))[0]
    return {
        "comparator": threshold.comparator,
        "comparator_label": label,
        "direction": direction(threshold),
        "rule": rule_text(threshold),
        "green": _json(threshold.green),
        "yellow": _json(threshold.yellow),
        "green_min": _json(threshold.green_min),
        "green_max": _json(threshold.green_max),
        "yellow_min": _json(threshold.yellow_min),
        "yellow_max": _json(threshold.yellow_max),
    }


def _json(value: Any) -> float | None:
    return None if value is None else float(value)


__all__ = ["Threshold", "from_kpi", "evaluate", "rule_text", "direction", "config", "COMPARATORS"]
