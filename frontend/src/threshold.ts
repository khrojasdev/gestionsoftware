/** Client-side mirror of the backend KPI threshold rules (for live preview). */

import { kpiValue } from "./format";
import type { Comparator, KpiStatus } from "./types";

export const COMPARATORS: { value: Comparator; label: string; hint: string }[] = [
  { value: "GE", label: "Mayor o igual (≥)", hint: "Más alto es mejor" },
  { value: "GT", label: "Mayor que (>)", hint: "Más alto es mejor (estricto)" },
  { value: "LE", label: "Menor o igual (≤)", hint: "Más bajo es mejor" },
  { value: "LT", label: "Menor que (<)", hint: "Más bajo es mejor (estricto)" },
  { value: "RANGE", label: "En rango", hint: "Verde dentro de un rango" },
  { value: "INFO", label: "Informativo", hint: "Sin semáforo" },
];

export type ThresholdDraft = {
  comparator: Comparator;
  green: string;
  yellow: string;
  greenMin: string;
  greenMax: string;
  yellowMin: string;
  yellowMax: string;
};

const SYMBOL: Record<string, string> = { GE: "≥", GT: ">", LE: "≤", LT: "<" };

function num(value: string): number | null {
  if (value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isNaN(parsed) ? null : parsed;
}

export function evaluateStatus(value: number | null, draft: ThresholdDraft): KpiStatus {
  if (value === null || value === undefined) return "SIN_DATOS";
  const { comparator } = draft;
  if (comparator === "INFO") return "INFO";
  if (comparator === "RANGE") {
    const gMin = num(draft.greenMin);
    const gMax = num(draft.greenMax);
    const yMin = num(draft.yellowMin);
    const yMax = num(draft.yellowMax);
    if (gMin !== null && gMax !== null && value >= gMin && value <= gMax) return "VERDE";
    const lo = yMin ?? gMin;
    const hi = yMax ?? gMax;
    if (lo !== null && hi !== null && value >= lo && value <= hi) return "AMARILLO";
    return "ROJO";
  }
  const green = num(draft.green);
  const yellow = num(draft.yellow);
  if (green === null || yellow === null) return "INFO";
  const higher = comparator === "GE" || comparator === "GT";
  const strict = comparator === "GT" || comparator === "LT";
  const ok = (limit: number) => (higher ? (strict ? value > limit : value >= limit) : strict ? value < limit : value <= limit);
  if (ok(green)) return "VERDE";
  if (ok(yellow)) return "AMARILLO";
  return "ROJO";
}

export function ruleText(draft: ThresholdDraft, unit: string | null): string {
  const { comparator } = draft;
  if (comparator === "INFO") return "Indicador informativo: se muestra el valor, sin semáforo.";
  if (comparator === "RANGE") {
    const g = `${kpiValue(num(draft.greenMin), unit)} y ${kpiValue(num(draft.greenMax), unit)}`;
    if (draft.yellowMin.trim() !== "" || draft.yellowMax.trim() !== "") {
      const y = `${kpiValue(num(draft.yellowMin), unit)} y ${kpiValue(num(draft.yellowMax), unit)}`;
      return `Verde si está entre ${g} · Amarillo si está entre ${y} · Rojo fuera de ese rango.`;
    }
    return `Verde si está entre ${g} · Rojo fuera de ese rango.`;
  }
  const green = num(draft.green);
  const yellow = num(draft.yellow);
  if (green === null || yellow === null) return "Define los umbrales verde y amarillo.";
  const symbol = SYMBOL[comparator];
  const strict = comparator === "GE" || comparator === "GT" ? "<" : ">";
  return `Verde si ${symbol} ${kpiValue(green, unit)} · Amarillo si ${symbol} ${kpiValue(yellow, unit)} · Rojo si ${strict} ${kpiValue(yellow, unit)}.`;
}

/** Build the API payload fields for the chosen comparator. */
export function thresholdPayload(draft: ThresholdDraft): Record<string, unknown> {
  const base: Record<string, unknown> = {
    comparator: draft.comparator,
    green_threshold: null,
    yellow_threshold: null,
    green_min: null,
    green_max: null,
    yellow_min: null,
    yellow_max: null,
  };
  if (draft.comparator === "RANGE") {
    base.green_min = num(draft.greenMin);
    base.green_max = num(draft.greenMax);
    base.yellow_min = num(draft.yellowMin);
    base.yellow_max = num(draft.yellowMax);
  } else if (draft.comparator !== "INFO") {
    base.green_threshold = num(draft.green);
    base.yellow_threshold = num(draft.yellow);
  }
  return base;
}

export function draftFromKpi(kpi: {
  comparator: Comparator;
  green_threshold: number | null;
  yellow_threshold: number | null;
  green_min: number | null;
  green_max: number | null;
  yellow_min: number | null;
  yellow_max: number | null;
}): ThresholdDraft {
  const s = (value: number | null) => (value === null || value === undefined ? "" : String(value));
  return {
    comparator: kpi.comparator,
    green: s(kpi.green_threshold),
    yellow: s(kpi.yellow_threshold),
    greenMin: s(kpi.green_min),
    greenMax: s(kpi.green_max),
    yellowMin: s(kpi.yellow_min),
    yellowMax: s(kpi.yellow_max),
  };
}
