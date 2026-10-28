/** Shapes returned by the `/api/v1` read models. */

export type Role = "ADMINISTRADOR" | "JEFE_DE_PROYECTO" | "INTEGRANTE";

export type User = {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  roles: Role[];
  created_at?: string;
};

export type LoginResponse = { access_token: string; token_type: string; expires_at: string; user: User };

export type ProjectStatus = "BORRADOR" | "ACTIVO" | "CERRADO" | "ARCHIVADO";

export type ProjectOverview = {
  id: string;
  code: string;
  name: string;
  client: string | null;
  status: ProjectStatus;
  planned_start: string | null;
  committed_finish: string | null;
  cutoff_date: string | null;
  budget: number | null;
  contingency_pct: number | null;
  working_hours_per_day: number | null;
  responsible_id: string | null;
  responsible: string | null;
  has_plan: boolean;
  progress_real: number | null;
  progress_plan: number | null;
  bac: number | null;
  ac: number | null;
  spi: number | null;
  cpi: number | null;
  baseline_finish: string | null;
  forecast_finish: string | null;
  start: string | null;
  baseline_version: string | null;
  counts: { stages: number; activities: number; subactivities: number; milestones: number };
  open_changes: number;
};

export type ElementKind = "ETAPA" | "ACTIVIDAD" | "SUBACTIVIDAD" | "HITO";
export type ElementStatus = "COMPLETADA" | "COMPLETADA_ATRASO" | "EN_CURSO" | "ATRASADA" | "EN_RIESGO" | "NO_INICIADA";
export type DepType = "FS" | "SS" | "FF" | "SF";

export type GanttElement = {
  id: string;
  external_id: string;
  kind: ElementKind;
  name: string;
  parent: string | null;
  level: number;
  order: number;
  start: string | null;
  finish: string | null;
  duration_days: number | null;
  baseline_start: string | null;
  baseline_finish: string | null;
  baseline_cost: number | null;
  forecast_start: string | null;
  forecast_finish: string | null;
  actual_start: string | null;
  actual_finish: string | null;
  progress: number;
  planned_pct: number;
  status: ElementStatus;
  status_label: string;
  slip_days: number;
  is_critical: boolean;
  total_slack: number | null;
  free_slack: number | null;
  planned_cost: number;
  actual_cost: number;
  predecessors: { id: string; predecessor: string; type: DepType; lag_days: number }[];
  resources: string[];
  children: number;
};

export type GanttLink = { id: string; from: string; to: string; type: DepType; lag_days: number; critical: boolean };

export type GanttFull = {
  project: ProjectOverview;
  cutoff: string | null;
  baseline_version: string | null;
  summary: {
    start: string | null;
    baseline_finish: string | null;
    plan_finish: string | null;
    forecast_finish: string | null;
    committed_finish: string | null;
    slip_days: number;
    reserve_days: number | null;
    critical_count: number;
  };
  holidays: string[];
  elements: GanttElement[];
  links: GanttLink[];
};

export type Change = {
  external_id: string;
  name: string;
  start_before: string | null;
  start_after: string | null;
  finish_before: string | null;
  finish_after: string | null;
  duration_before: number | null;
  duration_after: number | null;
  cost_before: number | null;
  cost_after: number | null;
};

export type ProjectFinish = { baseline: string | null; plan: string | null; forecast: string | null; start: string | null };

export type RecalcResult = { element?: string; changes: Change[]; finish_before: ProjectFinish | null; finish_after: ProjectFinish | null };

export type Allocation = {
  id: string;
  resource_id: string;
  resource: string;
  resource_external_id: string;
  resource_type: string;
  role: string | null;
  element_id: string;
  external_id: string;
  name: string;
  stage: string | null;
  hours: number | null;
  quantity: number | null;
  unit: string | null;
  hours_per_day: number | null;
  rate: number;
  cost: number;
  start: string | null;
  finish: string | null;
  duration_days: number | null;
  progress: number;
  status: ElementStatus;
};

export type ResourceRow = {
  id: string;
  external_id: string;
  name: string;
  type: string;
  role: string | null;
  rate: number;
  unit: string | null;
  capacity_hours_per_day: number | null;
  user_id: string | null;
  user: string | null;
  total_hours: number | null;
  total_quantity: number | null;
  planned_cost: number;
  task_count: number;
  peak_pct: number;
  overallocated_days: number;
  assignments: Allocation[];
};

export type Overallocation = {
  resource_id: string;
  resource: string;
  from: string;
  to: string;
  days: number;
  peak_pct: number;
  tasks: { external_id: string; name: string; hours_per_day: number }[];
};

export type ResourcesOverview = {
  resources: ResourceRow[];
  tasks: {
    element_id: string;
    external_id: string;
    name: string;
    stage: string | null;
    stage_name: string | null;
    start: string | null;
    finish: string | null;
    duration_days: number | null;
    planned_cost: number;
    actual_cost: number;
    progress: number;
    status: ElementStatus;
    assignments: Allocation[];
  }[];
  weeks: string[];
  load: {
    resource_id: string;
    name: string;
    role: string | null;
    weeks: { week: string; hours: number; capacity: number; pct: number; tasks: { external_id: string; name: string; hours: number }[] }[];
  }[];
  overallocations: Overallocation[];
  totals_by_type: Record<string, number>;
  totals_by_stage: { external_id: string; name: string; cost: number }[];
  total: number;
  calendar: { hours_per_day: number; working_days: number[]; holidays: { date: string; type: string; description: string | null }[] };
};

export type Evidence = { id: string; file_name: string; uploaded_at: string; size: number | null; uploaded_by: string | null };

export type Criterion = {
  id: string;
  external_id: string;
  description: string;
  verification_method: string;
  responsible: string | null;
  status: "PENDIENTE" | "CUMPLIDO" | "NO_CUMPLIDO";
  verified_by: string | null;
  verified_at: string | null;
  notes: string | null;
  evidences: Evidence[];
};

export type Milestone = {
  id: string;
  external_id: string;
  name: string;
  activity: string | null;
  stage: string | null;
  baseline_finish: string | null;
  finish: string | null;
  forecast_finish: string | null;
  actual_finish: string | null;
  progress: number;
  status: ElementStatus;
  status_label: string;
  slip_days: number;
  is_critical: boolean;
  acceptance_status: string;
  criteria_met: number;
  criteria_total: number;
  criteria: Criterion[];
  tasks: {
    external_id: string;
    name: string;
    kind: ElementKind;
    activity: string | null;
    progress: number;
    status: ElementStatus;
    status_label: string;
    finish: string | null;
    forecast_finish: string | null;
  }[];
};

export type MilestonesView = {
  cutoff: string | null;
  milestones: Milestone[];
  summary: { total: number; done: number; on_time_pct: number | null; at_risk: number; closing_deviation: number | null };
};

export type KpiStatus = "VERDE" | "AMARILLO" | "ROJO" | "INFO" | "SIN_DATOS";

export type Kpi = {
  id: string;
  code: string;
  name: string;
  description: string | null;
  formula: string;
  category: "PROYECTO" | "CAMBIO";
  category_label: string;
  is_additional: boolean;
  unit: string | null;
  scope: string;
  target: number | null;
  green_threshold: number | null;
  yellow_threshold: number | null;
  frequency: string | null;
  alert_rule: string | null;
  is_active: boolean;
  value: number | null;
  status: KpiStatus;
  direction: "MAYOR" | "MENOR" | null;
  breakdown: {
    formula: string;
    variables: Record<string, unknown>;
    substituted: string | null;
    value: number | null;
    error?: string | null;
    variables_detail?: { code: string; value: unknown; description: string; source: string; calculation: string }[];
  };
  history: { cutoff: string; value: number | null }[];
  versions: { version: number; formula: string; previous: string | null; changed_at: string | null; changed_by: string | null }[];
};

export type KpiBoard = {
  cutoff: string | null;
  kpis: Kpi[];
  variables: { code: string; description: string; source: string; calculation: string; type: string; value: unknown }[];
  manual: { code: string; label: string; value: number | null; updated_at: string | null }[];
};

export type ChangeStatus = "ABIERTA" | "APROBADA" | "RECHAZADA" | "CANCELADA" | "CERRADA";

export type ChangeRequest = {
  id: string;
  code: string;
  title: string;
  description: string;
  justification: string | null;
  type: string;
  type_label: string;
  priority: string;
  status: ChangeStatus;
  status_label: string;
  requester: string | null;
  requester_area: string | null;
  responsible: string | null;
  responsible_id: string | null;
  stage_sequence: number | null;
  stage_name: string | null;
  stages_completed: number;
  stages_total: number;
  sla_breached: boolean;
  delta_days: number | null;
  delta_cost: number | null;
  evidences: number;
  applied: boolean;
  created_at: string;
  decided_at: string | null;
  closed_at: string | null;
};

export type ChangeBoard = {
  requests: ChangeRequest[];
  stages: { id: string; name: string; sequence: number; sla_hours: number | null }[];
  users: { id: string; name: string }[];
};

export type ImpactRow = {
  task_id: string;
  name: string;
  start_before: string | null;
  start_after: string | null;
  finish_before: string | null;
  finish_after: string | null;
  duration_before: number | null;
  duration_after: number | null;
  cost_before: number | null;
  cost_after: number | null;
  critical: boolean;
};

export type Simulation = {
  baseline_id?: string;
  baseline_version: string | null;
  baseline_finish: string | null;
  proposed_finish: string | null;
  baseline_cost: number;
  proposed_cost: number;
  delta_schedule_days: number;
  delta_cost: number;
  contingency_amount: number;
  delta_contingency: number;
  contingency_consumption_pct: number | null;
  reserve_before: number | null;
  reserve_after: number | null;
  affected: ImpactRow[];
  resources: { resource: string; before: number; after: number; delta: number }[];
  critical_affected: boolean;
  summary: string;
};

export type ProposalItem = {
  task_id: string;
  duration_days?: number;
  start?: string;
  resources?: { resource: string; hours?: number; quantity?: number }[];
  note?: string;
};

export type ChangeDetail = {
  request: ChangeRequest;
  proposal: ProposalItem[];
  stages: {
    sequence: number;
    name: string;
    status: "PENDIENTE" | "ACTIVA" | "COMPLETADA" | "OMITIDA";
    entered_at: string | null;
    exited_at: string | null;
    sla_hours: number | null;
    elapsed_hours: number | null;
    breached: boolean;
    completed_by: string | null;
    notes: string | null;
  }[];
  transitions: { occurred_at: string; from_stage: string | null; to_stage: string | null; from_status: string | null; to_status: string | null; by: string | null; comment: string | null }[];
  audit: { occurred_at: string; action: string; by: string | null; data: Record<string, unknown> | null }[];
  impacts: {
    id: string;
    simulated_at: string;
    proposed_finish: string | null;
    delta_days: number;
    delta_cost: number;
    affected: ImpactRow[];
    resources: { resource: string; before: number; after: number; delta: number }[];
    summary: string | null;
  }[];
  preview: Simulation | null;
  evidences: Evidence[];
  contingency_amount: number;
  tasks: { external_id: string; name: string; duration_days: number | null; is_critical: boolean }[];
  resources: { external_id: string; name: string; type: string; rate: number }[];
  committed_finish: string | null;
};

export type ProjectDashboard = {
  cutoff: string | null;
  project: { name: string; code: string; committed_finish: string | null; budget: number | null };
  metrics: Record<string, number>;
  finish: { baseline: string | null; plan: string | null; forecast: string | null; start: string | null };
  reserve_days: number | null;
  late_count: number;
  milestones_done: number;
  milestones_total: number;
  stages: {
    external_id: string;
    name: string;
    planned_pct: number;
    progress: number;
    planned_cost: number;
    actual_cost: number;
    status: ElementStatus;
    forecast_finish: string | null;
    baseline_finish: string | null;
  }[];
  curve: { date: string; pv: number; ev: number | null; ac: number | null }[];
  late: {
    external_id: string;
    name: string;
    planned_pct: number;
    progress: number;
    forecast_finish: string | null;
    baseline_finish: string | null;
    slip_days: number;
    is_critical: boolean;
    status: ElementStatus;
    status_label: string;
  }[];
  milestones: { external_id: string; name: string; baseline: string | null; forecast: string | null; status: ElementStatus; progress: number }[];
  load: { name: string; peak_pct: number; hours: number; tasks: number }[];
  overallocations: Overallocation[];
  alerts: { level: "crit" | "warn" | "ok" | "info"; text: string }[];
  kpis: Record<string, { name: string; value: number | null; status: KpiStatus; unit: string | null; is_additional?: boolean }>;
};

export type ChangeDashboard = {
  cutoff: string | null;
  requests: ChangeRequest[];
  funnel: { sequence: number; name: string; count: number }[];
  stage_times: { sequence: number; name: string; avg_days: number | null; sla_days: number | null }[];
  by_status: Record<string, number>;
  by_type: Record<string, number>;
  risk: { code: string; title: string; impact: "BAJO" | "MEDIO" | "ALTO"; probability: "BAJA" | "MEDIA" | "ALTA"; status: ChangeStatus }[];
  alerts: { level: "crit" | "warn" | "ok" | "info"; text: string }[];
  metrics: Record<string, number>;
  contingency_amount: number;
  manual: Record<string, number>;
  kpis: Record<string, { name: string; value: number | null; status: KpiStatus; unit: string | null; is_additional?: boolean }>;
};

export type Checklist = {
  project: string;
  items: { label: string; value: number | string; required: number | string | null; ok: boolean }[];
  dependency_types: string[];
  resource_types: string[];
};

export type ImportPreview = {
  valid: boolean;
  report: { valid: boolean; errors: Issue[]; warnings: Issue[] };
  project_code: string;
  baseline_version: string;
  sheets: Record<string, number>;
  inspection: {
    format: "HORIZONTE" | "PLANTILLA";
    label: string;
    source_sheets: string[];
    sheets: { name: string; rows: number; found: string[]; expected: string[]; missing: string[]; converted: boolean }[];
  };
  project: Record<string, string>;
  summary: {
    elements: Record<string, number>;
    resources_human: number;
    resources_other: number;
    assignments: number;
    criteria: number;
    holidays: number;
    kpis: number;
  };
  sample: Record<string, unknown>[];
};

export type Issue = { severity: string; sheet: string | null; row: number | null; column: string | null; code: string; message: string };
