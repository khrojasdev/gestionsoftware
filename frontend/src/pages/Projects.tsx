import { useState } from "react";

import { api, errorMessage } from "../api";
import { useAuth } from "../auth";
import { Alert, Bar, Field, Icon, Modal, PageHeader, Tag, useToast } from "../components/ui";
import { d, moneyM, n, pct, PROJECT_STATUS_LABEL, statusTag } from "../format";
import { useProject } from "../project";
import { go } from "../router";
import type { ProjectOverview } from "../types";

type Draft = {
  code: string;
  name: string;
  client: string;
  status: string;
  planned_start: string;
  committed_finish: string;
  cutoff_date: string;
  budget: string;
  contingency_pct: string;
  working_hours_per_day: string;
};

function toDraft(project?: ProjectOverview): Draft {
  return {
    code: project?.code ?? "",
    name: project?.name ?? "",
    client: project?.client ?? "",
    status: project?.status ?? "BORRADOR",
    planned_start: project?.planned_start ?? "",
    committed_finish: project?.committed_finish ?? "",
    cutoff_date: project?.cutoff_date ?? "",
    budget: project?.budget != null ? String(project.budget) : "",
    contingency_pct: project?.contingency_pct != null ? String(project.contingency_pct) : "10",
    working_hours_per_day: project?.working_hours_per_day != null ? String(project.working_hours_per_day) : "8",
  };
}

export default function ProjectsPage() {
  const { projects, select, touch, project: current } = useProject();
  const { isManager, isAdmin } = useAuth();
  const toast = useToast();
  const [editing, setEditing] = useState<ProjectOverview | "new" | null>(null);
  const [removing, setRemoving] = useState<ProjectOverview | null>(null);

  async function close(project: ProjectOverview) {
    try {
      await api.patch(`/projects-admin/${project.id}`, { status: "CERRADO" });
      toast("ok", `Proyecto ${project.name} cerrado.`);
      touch();
    } catch (err) {
      toast("crit", errorMessage(err));
    }
  }

  return (
    <>
      <PageHeader crumb="General" title="Proyectos">
        {isManager && (
          <>
            <button className="btn" onClick={() => setEditing("new")}>
              <Icon name="plus" size={14} /> Proyecto vacío
            </button>
            <button className="btn pri" onClick={() => go("importar")}>
              <Icon name="upload" size={14} /> Importar Carta Gantt
            </button>
          </>
        )}
      </PageHeader>
      {!projects.length && (
        <div className="card card-b empty">
          Aún no hay proyectos. {isManager ? "Importa una Carta Gantt para comenzar." : "El Jefe de Proyecto debe crear o importar uno."}
        </div>
      )}
      <div className="grid g2">
        {projects.map((project) => {
          const slip = project.forecast_finish && project.committed_finish ? Math.round((Date.parse(project.committed_finish) - Date.parse(project.forecast_finish)) / 86_400_000) : null;
          return (
            <article key={project.id} className={`card proj-card ${current?.id === project.id ? "sel" : ""}`}>
              <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="mono muted" style={{ fontSize: 11 }}>
                    {project.code}
                  </div>
                  <h3>{project.name}</h3>
                  <div className="muted" style={{ fontSize: 12.5 }}>
                    {project.client ?? "Sin cliente"} · Responsable {project.responsible ?? "—"}
                  </div>
                </div>
                <Tag cls={statusTag(project.status)}>{PROJECT_STATUS_LABEL[project.status]}</Tag>
              </div>
              {project.has_plan ? (
                <>
                  <div>
                    <div style={{ display: "flex", fontSize: 12, marginBottom: 4 }}>
                      <span>
                        Avance real <b>{pct(project.progress_real, 1)}</b>
                      </span>
                      <span className="sp" style={{ flex: 1 }} />
                      <span className="muted">Planificado {pct(project.progress_plan, 1)}</span>
                    </div>
                    <Bar value={project.progress_real ?? 0} plan={project.progress_plan ?? 0} cls={(project.spi ?? 1) < 0.95 ? "late" : ""} />
                  </div>
                  <dl className="kv" style={{ gridTemplateColumns: "130px 1fr" }}>
                    <dt>Inicio · compromiso</dt>
                    <dd className="mono">
                      {d(project.start)} → {d(project.committed_finish)}
                    </dd>
                    <dt>Término proyectado</dt>
                    <dd>
                      <span className="mono">{d(project.forecast_finish)}</span>{" "}
                      {slip !== null && <Tag cls={slip < 0 ? "t-crit" : slip < 10 ? "t-warn" : "t-ok"}>{slip >= 0 ? `${slip} días corridos antes del compromiso` : `${-slip} días corridos tarde`}</Tag>}
                    </dd>
                    <dt>SPI · CPI</dt>
                    <dd className="mono">
                      {n(project.spi, 2)} · {n(project.cpi, 2)}
                    </dd>
                    <dt>Presupuesto (BAC)</dt>
                    <dd className="mono">
                      {moneyM(project.bac)} de {moneyM(project.budget)}
                    </dd>
                    <dt>Estructura</dt>
                    <dd>
                      {project.counts.stages} etapas · {project.counts.activities} actividades · {project.counts.subactivities} subactividades · {project.counts.milestones} hitos
                    </dd>
                    <dt>Línea base · corte</dt>
                    <dd className="mono">
                      {project.baseline_version ?? "—"} · {d(project.cutoff_date)}
                    </dd>
                    <dt>Cambios abiertos</dt>
                    <dd>{project.open_changes}</dd>
                  </dl>
                </>
              ) : (
                <Alert level="info">Proyecto sin planificación. Importa su Carta Gantt para calcular fechas, costos y KPI.</Alert>
              )}
              <div className="toolbar" style={{ margin: 0 }}>
                <button
                  className="btn dark sm"
                  onClick={() => {
                    select(project.id);
                    go(project.has_plan ? "tablero" : "importar");
                  }}
                >
                  {project.has_plan ? "Abrir tablero" : "Importar planificación"}
                </button>
                {project.has_plan && (
                  <button
                    className="btn sm"
                    onClick={() => {
                      select(project.id);
                      go("gantt");
                    }}
                  >
                    Carta Gantt
                  </button>
                )}
                <div className="sp" />
                {isManager && (
                  <button className="btn sm" onClick={() => setEditing(project)}>
                    <Icon name="edit" size={13} /> Editar
                  </button>
                )}
                {isManager && project.status === "ACTIVO" && (
                  <button className="btn sm" onClick={() => void close(project)} title="El cierre exige hitos cumplidos y cambios cerrados">
                    Cerrar
                  </button>
                )}
                {isAdmin && (
                  <button className="btn sm danger" onClick={() => setRemoving(project)}>
                    <Icon name="trash" size={13} />
                  </button>
                )}
              </div>
            </article>
          );
        })}
      </div>
      {editing && <ProjectModal project={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} onSaved={(id) => { setEditing(null); touch(); if (id) select(id); }} />}
      {removing && (
        <Modal
          title="Eliminar proyecto"
          onClose={() => setRemoving(null)}
          footer={
            <>
              <button className="btn" onClick={() => setRemoving(null)}>
                Cancelar
              </button>
              <button
                className="btn pri"
                onClick={async () => {
                  try {
                    await api.del(`/projects-admin/${removing.id}`);
                    toast("ok", `Proyecto ${removing.name} eliminado.`);
                    setRemoving(null);
                    touch();
                  } catch (err) {
                    toast("crit", errorMessage(err));
                  }
                }}
              >
                Eliminar definitivamente
              </button>
            </>
          }
        >
          <p>
            Se eliminará <b>{removing.name}</b> con su Gantt, recursos, líneas base, KPI, solicitudes de cambio y evidencias. Esta acción no se puede deshacer.
          </p>
        </Modal>
      )}
    </>
  );
}

function ProjectModal({ project, onClose, onSaved }: { project?: ProjectOverview; onClose: () => void; onSaved: (id?: string) => void }) {
  const [draft, setDraft] = useState<Draft>(toDraft(project));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (key: keyof Draft) => (event: { target: { value: string } }) => setDraft((value) => ({ ...value, [key]: event.target.value }));

  async function save() {
    setBusy(true);
    setError(null);
    const payload: Record<string, unknown> = {
      name: draft.name,
      client: draft.client || null,
      planned_start: draft.planned_start || null,
      committed_finish: draft.committed_finish || null,
      cutoff_date: draft.cutoff_date || null,
      budget: draft.budget ? Number(draft.budget) : null,
      contingency_pct: draft.contingency_pct ? Number(draft.contingency_pct) : null,
      working_hours_per_day: draft.working_hours_per_day ? Number(draft.working_hours_per_day) : null,
    };
    try {
      if (project) {
        if (draft.status !== project.status) payload.status = draft.status;
        await api.patch(`/projects-admin/${project.id}`, payload);
        onSaved();
      } else {
        const created = await api.post<ProjectOverview>("/projects-admin", { ...payload, code: draft.code, status: draft.status });
        onSaved(created.id);
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title={project ? `Editar ${project.name}` : "Nuevo proyecto"}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            Cancelar
          </button>
          <button className="btn pri" onClick={() => void save()} disabled={busy || !draft.name || (!project && !draft.code)}>
            {busy ? "Guardando…" : "Guardar"}
          </button>
        </>
      }
    >
      <div className="row">
        <Field label="Código">
          <input value={draft.code} onChange={set("code")} disabled={Boolean(project)} placeholder="EJ-001" />
        </Field>
        <Field label="Estado">
          <select value={draft.status} onChange={set("status")}>
            {Object.entries(PROJECT_STATUS_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <Field label="Nombre">
        <input value={draft.name} onChange={set("name")} />
      </Field>
      <Field label="Cliente">
        <input value={draft.client} onChange={set("client")} />
      </Field>
      <div className="row">
        <Field label="Inicio planificado">
          <input type="date" value={draft.planned_start} onChange={set("planned_start")} />
        </Field>
        <Field label="Término comprometido">
          <input type="date" value={draft.committed_finish} onChange={set("committed_finish")} />
        </Field>
        <Field label="Fecha de corte">
          <input type="date" value={draft.cutoff_date} onChange={set("cutoff_date")} />
        </Field>
      </div>
      <div className="row">
        <Field label="Presupuesto (CLP)">
          <input type="number" min={0} value={draft.budget} onChange={set("budget")} />
        </Field>
        <Field label="Contingencia (%)">
          <input type="number" min={0} max={100} value={draft.contingency_pct} onChange={set("contingency_pct")} />
        </Field>
        <Field label="Horas por día">
          <input type="number" min={1} max={24} value={draft.working_hours_per_day} onChange={set("working_hours_per_day")} />
        </Field>
      </div>
      {project && <p className="muted" style={{ fontSize: 12 }}>Cambiar la fecha de corte recalcula avance planificado, EVM y KPI. Cambiar el inicio reprograma todo el Gantt.</p>}
      {error && <Alert level="crit">{error}</Alert>}
    </Modal>
  );
}
