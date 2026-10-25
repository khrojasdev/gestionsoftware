"""Safe KPI formula parsing and the public KPI variable catalogue."""

from __future__ import annotations

import ast
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


class KpiFormulaError(ValueError):
    """Raised when a formula is outside the supported expression language."""


@dataclass(frozen=True, slots=True)
class KpiVariableDefinition:
    """Metadata displayed to users for a known KPI variable."""

    code: str
    description: str
    source: str
    calculation_method: str
    data_type: str = "DECIMAL"


DEFAULT_KPI_VARIABLES: tuple[KpiVariableDefinition, ...] = (
    KpiVariableDefinition("BAC", "Presupuesto al término", "Gantt y asignaciones", "Suma del costo planificado"),
    KpiVariableDefinition("PV", "Valor planificado", "Gantt y calendario", "Costo planificado por avance temporal"),
    KpiVariableDefinition("EV", "Valor ganado", "Avances registrados", "Costo planificado por avance real"),
    KpiVariableDefinition("AC", "Costo real", "Costos reales", "Suma de costos reales registrados"),
    KpiVariableDefinition("SPI", "Índice de desempeño del plazo", "EVM", "EV / PV"),
    KpiVariableDefinition("CPI", "Índice de desempeño del costo", "EVM", "EV / AC"),
    KpiVariableDefinition("SV", "Variación del plazo", "EVM", "EV - PV"),
    KpiVariableDefinition("CV", "Variación del costo", "EVM", "EV - AC"),
    KpiVariableDefinition("EAC", "Estimación al término", "EVM", "BAC / CPI"),
    KpiVariableDefinition("ETC", "Estimación para completar", "EVM", "EAC - AC"),
    KpiVariableDefinition("VAC", "Variación al término", "EVM", "BAC - EAC"),
    KpiVariableDefinition("PHYSICAL_PROGRESS_DEVIATION", "Desviación del avance físico", "Gantt", "Avance real menos avance planificado"),
    KpiVariableDefinition("LATE_ACTIVITIES_PCT", "Porcentaje de actividades atrasadas", "Gantt", "Actividades atrasadas sobre actividades totales"),
    KpiVariableDefinition("MILESTONES_ON_TIME_PCT", "Porcentaje de hitos cumplidos a tiempo", "Hitos", "Hitos cumplidos en o antes de su fecha planificada"),
    KpiVariableDefinition("CLOSING_MILESTONE_DEVIATION", "Desviación del hito de cierre", "Hitos", "Días entre fecha real y planificada del cierre"),
    KpiVariableDefinition("AVANCE_REAL", "Avance físico real", "Gantt", "Promedio ponderado de avance real"),
    KpiVariableDefinition("AVANCE_PLAN", "Avance físico planificado", "Gantt", "Avance temporal planificado"),
    KpiVariableDefinition("ACTIVIDADES_ATRASADAS", "Actividades atrasadas", "Gantt", "Conjunto de actividades atrasadas", "LIST"),
    KpiVariableDefinition("ACTIVIDADES", "Actividades", "Gantt", "Conjunto de actividades", "LIST"),
    KpiVariableDefinition("HITOS_A_TIEMPO", "Hitos a tiempo", "Hitos", "Conjunto de hitos cumplidos a tiempo", "LIST"),
    KpiVariableDefinition("HITOS", "Hitos", "Hitos", "Conjunto de hitos", "LIST"),
    KpiVariableDefinition("FECHA_CIERRE_REAL", "Fecha real de cierre", "Hitos", "Fecha de término real expresada como día", "DECIMAL"),
    KpiVariableDefinition("FECHA_CIERRE_BASE", "Fecha base de cierre", "Línea base", "Fecha de término planificada expresada como día", "DECIMAL"),
    KpiVariableDefinition("ADVANCE_GAP", "Desviación de avance físico", "Gantt", "avance_real - avance_plan"),
    KpiVariableDefinition("LATE_TASKS", "Actividades atrasadas", "Gantt", "count(actividades_atrasadas) / count(actividades)"),
    KpiVariableDefinition("MILESTONE_ON_TIME", "Hitos cumplidos a tiempo", "Hitos", "count(hitos_a_tiempo) / count(hitos)"),
    KpiVariableDefinition("CLOSE_VARIANCE", "Desviación del hito de cierre", "Hitos", "fecha_cierre_real - fecha_cierre_base"),
    KpiVariableDefinition("CHANGE_REQUESTS", "Solicitudes registradas", "Gestión del cambio", "Conteo de solicitudes del proyecto"),
    KpiVariableDefinition("CHANGE_APPROVAL_RATE", "Tasa de aprobación", "Gestión del cambio", "Solicitudes aprobadas sobre solicitudes decididas"),
    KpiVariableDefinition("CHANGE_REJECTION_RATE", "Tasa de rechazo", "Gestión del cambio", "Solicitudes rechazadas sobre solicitudes decididas"),
    KpiVariableDefinition("CHANGE_AVG_CYCLE_HOURS", "Tiempo medio de ciclo", "Gestión del cambio", "Promedio de horas desde registro hasta cierre"),
    KpiVariableDefinition("CHANGE_AVG_IMPACT_HOURS", "Tiempo medio de evaluación de impacto", "Gestión del cambio", "Promedio entre registro y simulación de impacto"),
    KpiVariableDefinition("CHANGE_IMPACT_COST", "Impacto acumulado en costo", "Gestión del cambio", "Suma de deltas de costo de impactos"),
    KpiVariableDefinition("CHANGE_IMPACT_DAYS", "Impacto acumulado en plazo", "Gestión del cambio", "Suma de deltas de plazo de impactos"),
    KpiVariableDefinition("CHANGE_EVIDENCE_COMPLETE_PCT", "Porcentaje con evidencia completa", "Gestión del cambio", "Solicitudes con evidencia sobre solicitudes totales"),
    KpiVariableDefinition("CHANGE_SLA_BREACHES", "Solicitudes fuera de SLA", "Gestión del cambio", "Conteo de solicitudes con etapa vencida"),
    KpiVariableDefinition("CHANGE_CONTINGENCY_CONSUMPTION", "Consumo de contingencia", "Gestión del cambio", "Impacto de contingencia sobre presupuesto de contingencia"),
    KpiVariableDefinition("CHANGE_ADOPTION_INDEX", "Índice de adopción", "Gestión del cambio", "Indicador registrado de adopción"),
    KpiVariableDefinition("CHANGE_TRAINING_COVERAGE", "Cobertura de capacitación", "Gestión del cambio", "Porcentaje de usuarios capacitados"),
    *(KpiVariableDefinition(f"VALOR_{index:02d}", f"Variable de KPI de cambio {index:02d}", "Gestión del cambio", "Valor calculado del indicador de cambio") for index in range(1, 13)),
)

_FUNCTIONS = {"sum", "avg", "min", "max", "count", "if"}
_IF_CALL_PATTERN = re.compile(r"\bif\s*\(", re.IGNORECASE)
_COMPARISON_OPERATORS = (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE)


def _decimal(value: object) -> Decimal:
    if isinstance(value, bool):
        raise KpiFormulaError("Los booleanos no son valores KPI")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as error:
        raise KpiFormulaError("El valor no es numérico") from error


def validate_formula(formula: str, variable_codes: Sequence[str]) -> ast.AST:
    """Parse and validate a formula without executing user supplied code."""

    normalized = _IF_CALL_PATTERN.sub("IF(", formula.strip())
    if not normalized:
        raise KpiFormulaError("La fórmula no puede estar vacía")
    try:
        tree = ast.parse(normalized, mode="eval")
    except SyntaxError as error:
        raise KpiFormulaError("La fórmula KPI no tiene una sintaxis válida") from error
    allowed = {code.upper() for code in variable_codes}
    _validate_node(tree.body, allowed)
    return tree.body


def evaluate_formula(formula: str, values: Mapping[str, object], variable_codes: Sequence[str] | None = None) -> Decimal | bool:
    """Evaluate the restricted AST language; this function never calls eval()."""

    aliases = {key.upper(): value for key, value in values.items()}
    codes = variable_codes or tuple(aliases)
    tree = validate_formula(formula, codes)
    return _evaluate(tree, aliases)


def formula_variables(formula: str) -> tuple[str, ...]:
    """Return variable names referenced by a validated formula."""

    normalized = _IF_CALL_PATTERN.sub("IF(", formula.strip())
    try:
        tree = ast.parse(normalized, mode="eval")
    except SyntaxError as error:
        raise KpiFormulaError("La fórmula KPI no tiene una sintaxis válida") from error
    return tuple(sorted({node.id.upper() for node in ast.walk(tree) if isinstance(node, ast.Name) and node.id.upper() not in _FUNCTIONS}))


def _validate_node(node: ast.AST, allowed: set[str]) -> None:
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, int | float) or isinstance(node.value, bool):
            raise KpiFormulaError("Solo se permiten números en una fórmula KPI")
        return
    if isinstance(node, ast.Name):
        if node.id.upper() not in allowed and node.id.upper() not in {name.upper() for name in _FUNCTIONS}:
            raise KpiFormulaError(f"Variable KPI no registrada: {node.id}")
        return
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd | ast.USub):
        _validate_node(node.operand, allowed)
        return
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add | ast.Sub | ast.Mult | ast.Div):
        _validate_node(node.left, allowed)
        _validate_node(node.right, allowed)
        return
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And | ast.Or):
        for value in node.values:
            _validate_node(value, allowed)
        return
    if isinstance(node, ast.Compare) and all(isinstance(op, _COMPARISON_OPERATORS) for op in node.ops):
        _validate_node(node.left, allowed)
        for comparator in node.comparators:
            _validate_node(comparator, allowed)
        return
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id.lower() in _FUNCTIONS:
        if node.keywords:
            raise KpiFormulaError("Las funciones KPI no aceptan argumentos nombrados")
        for argument in node.args:
            _validate_node(argument, allowed)
        return
    raise KpiFormulaError("La expresión KPI contiene una operación no permitida")


def _evaluate(node: ast.AST, values: Mapping[str, object]) -> Decimal | bool | list[object]:
    if isinstance(node, ast.Constant):
        return _decimal(node.value)
    if isinstance(node, ast.Name):
        key = node.id.upper()
        if key not in values:
            raise KpiFormulaError(f"No hay valor disponible para la variable KPI: {node.id}")
        return values[key]
    if isinstance(node, ast.UnaryOp):
        value = _decimal(_evaluate(node.operand, values))
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp):
        left = _decimal(_evaluate(node.left, values))
        right = _decimal(_evaluate(node.right, values))
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if right == 0:
            raise KpiFormulaError("La fórmula KPI no puede dividir por cero")
        return left / right
    if isinstance(node, ast.Compare):
        left = _evaluate(node.left, values)
        for operation, comparator in zip(node.ops, node.comparators, strict=True):
            right = _evaluate(comparator, values)
            if not _compare(operation, left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.BoolOp):
        evaluated = [_evaluate(value, values) for value in node.values]
        return all(bool(value) for value in evaluated) if isinstance(node.op, ast.And) else any(bool(value) for value in evaluated)
    if isinstance(node, ast.Call):
        arguments = [_evaluate(argument, values) for argument in node.args]
        return _call(node.func.id.lower(), arguments)
    raise KpiFormulaError("La expresión KPI contiene una operación no permitida")


def _compare(operation: ast.cmpop, left: object, right: object) -> bool:
    left_decimal, right_decimal = _decimal(left), _decimal(right)
    return {
        ast.Eq: left_decimal == right_decimal,
        ast.NotEq: left_decimal != right_decimal,
        ast.Lt: left_decimal < right_decimal,
        ast.LtE: left_decimal <= right_decimal,
        ast.Gt: left_decimal > right_decimal,
        ast.GtE: left_decimal >= right_decimal,
    }[type(operation)]


def _call(name: str, arguments: list[object]) -> Decimal:
    if name == "if":
        if len(arguments) != 3:
            raise KpiFormulaError("if requiere condición, valor verdadero y valor falso")
        return _decimal(arguments[1] if bool(arguments[0]) else arguments[2])
    if name == "count":
        if len(arguments) != 1:
            raise KpiFormulaError("count requiere un argumento")
        value = arguments[0]
        return Decimal(str(len(value))) if isinstance(value, list | tuple | set | dict) else Decimal("1")
    values = [_decimal(item) for argument in arguments for item in (argument if isinstance(argument, list | tuple | set) else [argument])]
    if not values:
        raise KpiFormulaError(f"{name} requiere al menos un valor")
    if name == "sum":
        return sum(values, Decimal("0"))
    if name == "avg":
        return sum(values, Decimal("0")) / Decimal(len(values))
    if name == "min":
        return min(values)
    return max(values)
