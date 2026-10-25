export type ViewKey = "overview" | "resources" | "kpis" | "boards" | "users";

export const PROJECT_ID = "3c5d52b4-5183-454f-8fa2-0c5e72216eb1";
const API_URL = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(public readonly status: number, message: string, public readonly details?: unknown) {
    super(message);
    this.name = "ApiError";
  }
}

export type Resource = {
  id: string;
  name: string;
  initials: string;
  role: string;
  kind: "Persona" | "Equipo";
  capacity: number;
  assigned: number;
  costPlan: number;
  costActual: number;
  color: string;
  apiType: string;
};

export type TaskStatus = "En curso" | "Próxima" | "Riesgo" | "Completada";
export type Task = {
  id: string;
  apiId: string;
  name: string;
  resource: string;
  status: TaskStatus;
  progress: number;
  hours: number;
  planCost: number;
  actualCost: number;
  due: string;
  start: string | null;
  finish: string | null;
  durationDays: number;
  parentId: string | null;
  kind: string;
  critical: boolean;
};

export type GanttElement = {
  id: string;
  external_id: string;
  element_type: string;
  name: string;
  parent_id: string | null;
  parent_external_id: string | null;
  planned_start: string | null;
  planned_finish: string | null;
  duration_days: number | null;
  progress_pct: number;
  planned_cost: number;
  actual_cost: number;
  effort_hours: number | null;
  is_critical: boolean;
};

export type Kpi = {
  id: string;
  label: string;
  value: string;
  change: string;
  trend: "up" | "down" | "steady";
  target: string;
  status: "healthy" | "warning" | "critical";
  formula: string;
  unit: string;
  history: number[];
  code: string;
};

export type ChangeCard = {
  id: string;
  title: string;
  owner: string;
  impact: string;
  age: string;
  priority: "Alta" | "Media" | "Baja";
  avatar: string;
  status: string;
  description: string;
};

type Envelope<T> = { data: T; meta?: Record<string, unknown> };
type RawResource = { id: string; external_id: string; name: string; resource_type: string; role?: string | null; rate?: number; capacity_hours_per_day?: number | null };
type RawKpi = { id: string; code: string; name: string; formula: string; target?: number | null; scope?: string; [key: string]: unknown };
type RawChange = { id: string; title: string; code: string; description: string; priority: string; status: string; created_at: string; requester_id?: string | null };
type RawCosts = { by_task?: Record<string, { planned_cost?: number; actual_cost?: number }> };

async function request<T>(path: string, token?: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "No se pudo conectar con la API FastAPI");
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string; error?: { message?: string; details?: unknown } };
    throw new ApiError(response.status, body.error?.message ?? body.detail ?? `La API respondió ${response.status}`, body.error?.details);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const unwrap = <T,>(response: Envelope<T>): T => response.data;
const initials = (name: string) => name.split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase();
const moneyNumber = (value: unknown) => typeof value === "number" ? value : Number(value ?? 0);
const dateLabel = (value: string | null) => value ? new Date(`${value}T00:00:00`).toLocaleDateString("es-CL", { day: "2-digit", month: "short", year: "numeric" }).replace(".", "") : "Sin fecha";

function mapResource(item: RawResource, index: number): Resource {
  const capacity = moneyNumber(item.capacity_hours_per_day) * 5 || 40;
  return { id: item.id, name: item.name, initials: initials(item.name), role: item.role ?? "Sin rol", kind: item.resource_type === "HUMANO" ? "Persona" : "Equipo", capacity, assigned: 0, costPlan: 0, costActual: 0, color: ["#6c63ff", "#e78a5c", "#55a889", "#d5a63e", "#a879ce"][index % 5], apiType: item.resource_type };
}

function mapTask(item: GanttElement): Task {
  const progress = moneyNumber(item.progress_pct);
  return { id: item.external_id, apiId: item.id, name: item.name, resource: "Sin asignar", status: progress >= 100 ? "Completada" : progress > 0 ? "En curso" : "Próxima", progress, hours: moneyNumber(item.effort_hours), planCost: moneyNumber(item.planned_cost), actualCost: moneyNumber(item.actual_cost), due: dateLabel(item.planned_finish), start: item.planned_start, finish: item.planned_finish, durationDays: item.duration_days ?? 0, parentId: item.parent_external_id, kind: item.element_type, critical: Boolean(item.is_critical) };
}

function mapKpi(item: RawKpi): Kpi {
  return { id: item.id, code: item.code, label: item.name, value: "—", change: "Sin histórico", trend: "steady", target: item.target == null ? "—" : String(item.target), status: "healthy", formula: item.formula, unit: item.scope ?? "PROYECTO", history: [] };
}

function mapChange(item: RawChange): ChangeCard {
  const status = item.status;
  const bucket = status === "APROBADA" || status === "CERRADA" ? "approved" : status === "RECHAZADA" || status === "CANCELADA" ? "rejected" : status === "ABIERTA" ? "incoming" : "analysis";
  const age = item.created_at ? new Date(item.created_at).toLocaleDateString("es-CL") : "—";
  return { id: item.id, title: item.title, owner: item.requester_id ?? "Solicitante no informado", impact: "Impacto pendiente de simulación", age, priority: item.priority === "ALTA" || item.priority === "CRITICA" ? "Alta" : item.priority === "BAJA" ? "Baja" : "Media", avatar: "—", status: bucket, description: item.description };
}

export type F6Data = { resources: Resource[]; tasks: Task[]; kpis: Kpi[]; changeCards: Record<string, ChangeCard[]> };

export async function getF6Data(projectId = PROJECT_ID, token?: string): Promise<F6Data> {
  const [resourceResponse, ganttResponse, kpiResponse, changeResponse, costResponse] = await Promise.all([
    request<Envelope<RawResource[]>>(`/api/v1/projects/${projectId}/resources`, token),
    request<Envelope<GanttElement[]>>(`/api/v1/projects/${projectId}/gantt`, token),
    request<Envelope<RawKpi[]>>(`/api/v1/projects/${projectId}/kpis`, token),
    request<Envelope<RawChange[]>>(`/api/v1/projects/${projectId}/changes`, token),
    request<Envelope<RawCosts>>(`/api/v1/projects/${projectId}/costs`, token),
  ]);
  const resources = unwrap(resourceResponse).map(mapResource);
  const costs = unwrap(costResponse).by_task ?? {};
  const tasks = unwrap(ganttResponse).map(mapTask).map((task) => ({ ...task, planCost: moneyNumber(costs[task.id]?.planned_cost ?? task.planCost), actualCost: moneyNumber(costs[task.id]?.actual_cost ?? task.actualCost) }));
  const changes = unwrap(changeResponse).map(mapChange);
  const changeCards: Record<string, ChangeCard[]> = { incoming: [], analysis: [], approved: [], rejected: [] };
  changes.forEach((change) => changeCards[change.status]?.push(change));
  return { resources, tasks, kpis: unwrap(kpiResponse).map(mapKpi), changeCards };
}

export async function getGantt(projectId: string, token?: string): Promise<GanttElement[]> { return unwrap(await request<Envelope<GanttElement[]>>(`/api/v1/projects/${projectId}/gantt`, token)); }
export async function updateGanttElement(projectId: string, elementId: string, patch: { duration_days?: number; planned_start?: string; planned_finish?: string; progress_pct?: number }, token?: string): Promise<GanttElement> { return unwrap(await request<Envelope<GanttElement>>(`/api/v1/projects/${projectId}/gantt/${elementId}`, token, { method: "PATCH", body: JSON.stringify(patch) })); }
export async function recalculateProject(projectId: string, token?: string): Promise<unknown> { return unwrap(await request<Envelope<unknown>>(`/api/v1/projects/${projectId}/recalculate`, token, { method: "POST" })); }
export async function assignResource(projectId: string, elementId: string, resourceId: string, plannedHours: number, token?: string): Promise<unknown> { return unwrap(await request<Envelope<unknown>>(`/api/v1/projects/${projectId}/assignments`, token, { method: "POST", body: JSON.stringify({ element_id: elementId, resource_id: resourceId, planned_hours: plannedHours }) })); }
export async function transitionChange(projectId: string, changeId: string, status: "APROBADA" | "RECHAZADA", token?: string): Promise<ChangeCard> { return mapChange(unwrap(await request<Envelope<RawChange>>(`/api/v1/projects/${projectId}/changes/${changeId}/transition`, token, { method: "POST", body: JSON.stringify({ status }) })));
}
export async function previewImport(sourcePath: string, token?: string): Promise<Record<string, unknown>> { return unwrap(await request<Envelope<Record<string, unknown>>>("/api/v1/projects/import/preview", token, { method: "POST", body: JSON.stringify({ source_path: sourcePath }) })); }
export async function importProjectVersion(projectId: string, sourcePath: string, token?: string): Promise<Record<string, unknown>> { return unwrap(await request<Envelope<Record<string, unknown>>>(`/api/v1/projects/${projectId}/imports`, token, { method: "POST", body: JSON.stringify({ source_path: sourcePath }) })); }

export { API_URL };
