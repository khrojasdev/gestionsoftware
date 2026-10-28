/** Formatting helpers (Chilean conventions: dd-mm-aaaa, CLP with thousands dots). */

import type { ElementStatus, KpiStatus } from "./types";

const intFmt = new Intl.NumberFormat("es-CL", { maximumFractionDigits: 0 });
const dec1 = new Intl.NumberFormat("es-CL", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const dec2 = new Intl.NumberFormat("es-CL", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function d(value: string | null | undefined): string {
  if (!value) return "—";
  const [y, m, day] = value.slice(0, 10).split("-");
  return `${day}-${m}-${y}`;
}

export function dShort(value: string | null | undefined): string {
  if (!value) return "—";
  const [, m, day] = value.slice(0, 10).split("-");
  return `${day}-${m}`;
}

export function dt(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(date.getDate())}-${pad(date.getMonth() + 1)}-${date.getFullYear()} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function money(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const rounded = Math.round(value);
  return `${rounded < 0 ? "−" : ""}$${intFmt.format(Math.abs(rounded))}`;
}

export function moneyM(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value < 0 ? "−" : ""}$${dec1.format(Math.abs(value) / 1_000_000)} M`;
}

export function signedMoney(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${value > 0 ? "+" : value < 0 ? "−" : ""}${money(Math.abs(value))}`;
}

export function n(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (digits === 1) return dec1.format(value);
  if (digits === 2) return dec2.format(value);
  if (digits > 2) return new Intl.NumberFormat("es-CL", { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
  return intFmt.format(value);
}

export function pct(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${n(value, digits)} %`;
}

export function signed(value: number | null | undefined, suffix = ""): string {
  if (value === null || value === undefined) return "—";
  return `${value > 0 ? "+" : value < 0 ? "−" : "±"}${n(Math.abs(value))}${suffix}`;
}

/** Display a KPI value respecting its unit. */
export function kpiValue(value: number | null | undefined, unit: string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  switch ((unit ?? "").toLowerCase()) {
    case "clp":
      return money(value);
    case "%":
      return pct(value, 1);
    case "pp":
      return `${n(value, 1)} pp`;
    case "índice":
    case "indice":
      return n(value, 2);
    case "días":
    case "dias":
      return `${n(value, 1)} d`;
    case "h":
      return `${n(value, 1)} h`;
    default:
      return Math.abs(value) >= 1000 ? n(value) : n(value, Number.isInteger(value) ? 0 : 2);
  }
}

export function statusTag(status: ElementStatus | string): string {
  switch (status) {
    case "COMPLETADA":
    case "CUMPLIDO":
    case "CERRADA":
    case "APROBADA":
    case "ACTIVO":
      return "t-ok";
    case "COMPLETADA_ATRASO":
    case "EN_RIESGO":
    case "PENDIENTE":
      return "t-warn";
    case "ATRASADA":
    case "NO_CUMPLIDO":
    case "RECHAZADA":
      return "t-crit";
    case "EN_CURSO":
    case "ABIERTA":
      return "t-info";
    default:
      return "t-mute";
  }
}

export function kpiTag(status: KpiStatus): string {
  return { VERDE: "t-ok", AMARILLO: "t-warn", ROJO: "t-crit", INFO: "t-info", SIN_DATOS: "t-mute" }[status] ?? "t-mute";
}

export function kpiDot(status: KpiStatus): string {
  return { VERDE: "d-ok", AMARILLO: "d-warn", ROJO: "d-crit", INFO: "d-info", SIN_DATOS: "" }[status] ?? "";
}

export const KPI_LABEL: Record<KpiStatus, string> = {
  VERDE: "Verde",
  AMARILLO: "Amarillo",
  ROJO: "Rojo",
  INFO: "Informativo",
  SIN_DATOS: "Sin datos",
};

export const ROLE_LABEL: Record<string, string> = {
  ADMINISTRADOR: "Administrador",
  JEFE_DE_PROYECTO: "Jefe de Proyecto",
  INTEGRANTE: "Integrante",
};

export const RESOURCE_TYPE_LABEL: Record<string, string> = {
  HUMANO: "Humano",
  EQUIPAMIENTO: "Equipamiento",
  INFRAESTRUCTURA_LICENCIA: "Infraestructura / licencia",
  SERVICIO_EXTERNO: "Servicio externo",
};

export const PROJECT_STATUS_LABEL: Record<string, string> = {
  BORRADOR: "Borrador",
  ACTIVO: "En ejecución",
  CERRADO: "Cerrado",
  ARCHIVADO: "Archivado",
};

export function initials(name: string | null | undefined): string {
  if (!name) return "?";
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export function toDate(value: string): Date {
  const [y, m, day] = value.slice(0, 10).split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, day));
}

export function daysBetween(a: string, b: string): number {
  return Math.round((toDate(b).getTime() - toDate(a).getTime()) / 86_400_000);
}

export function addDays(value: string, days: number): string {
  const date = toDate(value);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function fileSize(bytes: number | null | undefined): string {
  if (!bytes) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${n(bytes / 1024)} KB`;
  return `${n(bytes / 1024 / 1024, 1)} MB`;
}
