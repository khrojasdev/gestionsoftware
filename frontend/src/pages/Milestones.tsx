import { useEffect, useRef, useState } from "react";

import { api, downloadFile, errorMessage } from "../api";
import { useAuth } from "../auth";
import { Alert, Bar, Card, ErrorBox, Field, Icon, Loading, Modal, PageHeader, Tag, useLoad, useToast } from "../components/ui";
import { d, dShort, dt, fileSize, n, pct, statusTag } from "../format";
import { useProject } from "../project";
import { href } from "../router";
import type { Criterion, Milestone, MilestonesView } from "../types";

const CRITERION_LABEL: Record<string, string> = { PENDIENTE: "Pendiente", CUMPLIDO: "Cumplido", NO_CUMPLIDO: "No cumplido" };

export default function MilestonesPage({ focus }: { focus: string | null }) {
  const { projectId, version, touch } = useProject();
  const { data, error, loading, reload } = useLoad(() => api.get<MilestonesView>(`/projects/${projectId}/milestones`), [projectId, version]);
  const [open, setOpen] = useState<Set<string>>(new Set(focus ? [focus] : []));

  const [lastFocus, setLastFocus] = useState(focus);
  if (focus !== lastFocus) {
    setLastFocus(focus);
    if (focus) setOpen((current) => new Set([...current, focus]));
  }
  useEffect(() => {
    if (focus) setTimeout(() => document.getElementById(`ms-${focus}`)?.scrollIntoView({ behavior: "smooth", block: "start" }), 250);
  }, [focus]);

  if (loading && !data) return <Loading />;
  if (error || !data) return <ErrorBox error={error ?? "Sin datos"} onRetry={() => void reload()} />;
  const { summary, milestones } = data;
  const dates = milestones.flatMap((item) => [item.baseline_finish, item.forecast_finish]).filter(Boolean) as string[];
  dates.sort();
  const first = dates[0];
  const last = dates[dates.length - 1];
  const span = first && last ? Math.max(1, Date.parse(last) - Date.parse(first)) : 1;
  const position = (date: string | null) => (date && first ? ((Date.parse(date) - Date.parse(first)) / span) * 100 : 0);

  const toggle = (id: string) =>
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <>
      <PageHeader crumb="Planificación" title="Hitos y criterios de aceptación">
        <button className="btn" onClick={() => setOpen(new Set(milestones.map((item) => item.external_id)))}>
          Expandir todos
        </button>
      </PageHeader>
      <div className="grid g4" style={{ marginBottom: 16 }}>
        <div className="card kpi">
          <div className="l">Hitos cumplidos</div>
          <div className="v">
            {summary.done} / {summary.total}
          </div>
          <Bar value={(summary.done / Math.max(summary.total, 1)) * 100} />
        </div>
        <div className="card kpi">
          <div className="l">
            <span className={`dot ${(summary.on_time_pct ?? 0) >= 90 ? "d-ok" : "d-warn"}`} /> Cumplidos a tiempo
          </div>
          <div className="v">{pct(summary.on_time_pct)}</div>
          <div className="s">sobre los hitos ya cumplidos</div>
        </div>
        <div className="card kpi">
          <div className="l">
            <span className={`dot ${summary.at_risk ? "d-warn" : "d-ok"}`} /> Hitos desplazados
          </div>
          <div className="v">{summary.at_risk}</div>
          <div className="s">proyección posterior a la línea base</div>
        </div>
        <div className="card kpi">
          <div className="l">
            <span className={`dot ${(summary.closing_deviation ?? 0) > 0 ? "d-warn" : "d-ok"}`} /> Desviación hito de cierre
          </div>
          <div className="v">{summary.closing_deviation !== null ? `${n(summary.closing_deviation)} días` : "—"}</div>
          <div className="s">hábiles respecto de la línea base</div>
        </div>
      </div>
      <Card title="Línea de tiempo (línea base vs proyección)" className="tl-card">
        <div className="tl2">
          <div className="ln" />
          {milestones.map((item, index) => {
            const cls = item.progress >= 100 ? "done" : item.slip_days > 0 ? "late" : "";
            return (
              <button key={item.id} className={`m ${cls} ${index % 2 ? "up" : ""}`} style={{ left: `${position(item.forecast_finish ?? item.finish)}%` }} onClick={() => toggle(item.external_id)} title={`${item.external_id} · ${item.name}`}>
                <span className="dm" />
                <b>{item.external_id}</b>
                <span>{dShort(item.forecast_finish ?? item.finish)}</span>
              </button>
            );
          })}
        </div>
        <div className="legend" style={{ border: 0, padding: "4px 0 0" }}>
          <span>
            <i className="lg" style={{ background: "var(--ok)", width: 10 }} /> Cumplido
          </span>
          <span>
            <i className="lg" style={{ background: "var(--warn)", width: 10 }} /> Desplazado
          </span>
          <span>
            <i className="lg" style={{ background: "var(--plan)", width: 10 }} /> Pendiente en plazo
          </span>
        </div>
      </Card>
      <div className="grid" style={{ marginTop: 16, gap: 10 }}>
        {milestones.map((item) => (
          <MilestoneCard
            key={item.id}
            milestone={item}
            open={open.has(item.external_id)}
            onToggle={() => toggle(item.external_id)}
            onChanged={() => {
              touch();
            }}
          />
        ))}
      </div>
    </>
  );
}

function MilestoneCard({ milestone, open, onToggle, onChanged }: { milestone: Milestone; open: boolean; onToggle: () => void; onChanged: () => void }) {
  const { isManager } = useAuth();
  const [adding, setAdding] = useState(false);
  const accepted = milestone.criteria_total > 0 && milestone.criteria_met === milestone.criteria_total;
  return (
    <section className={`card acc ${open ? "open" : ""}`} id={`ms-${milestone.external_id}`}>
      <button className="acc-h" onClick={onToggle} aria-expanded={open}>
        <span className={`diamond big ${milestone.progress >= 100 ? "done" : milestone.slip_days > 0 ? "late" : ""}`} />
        <span className="mono muted" style={{ width: 36 }}>
          {milestone.external_id}
        </span>
        <span style={{ flex: 1, minWidth: 0, textAlign: "left" }}>
          <b style={{ fontWeight: 600 }}>{milestone.name}</b>
          <span className="sub muted">
            {milestone.stage} · {milestone.activity}
          </span>
        </span>
        <span className="mono" style={{ fontSize: 12, textAlign: "right" }}>
          <span className="muted">Base</span> {d(milestone.baseline_finish)}
          <br />
          <span className="muted">Proy.</span> {d(milestone.actual_finish ?? milestone.forecast_finish)}
        </span>
        <span style={{ width: 120, textAlign: "right" }}>
          <Tag cls={statusTag(milestone.status)}>{milestone.status_label}</Tag>
          {milestone.slip_days > 0 && milestone.progress < 100 && (
            <div className="sub warn-txt" style={{ marginTop: 3 }}>
              +{milestone.slip_days} días hábiles
            </div>
          )}
        </span>
        <span style={{ width: 120 }}>
          <Tag cls={accepted ? "t-ok" : milestone.criteria_met ? "t-warn" : "t-mute"}>
            {milestone.criteria_met}/{milestone.criteria_total} criterios
          </Tag>
        </span>
        <span className="muted">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="acc-b">
          <div className="grid g2">
            <div>
              <h4 className="h4">Tareas que componen el hito</h4>
              <table className="t">
                <thead>
                  <tr>
                    <th>Tarea</th>
                    <th>Término</th>
                    <th>Avance</th>
                  </tr>
                </thead>
                <tbody>
                  {milestone.tasks.map((task) => (
                    <tr key={task.external_id}>
                      <td>
                        <a className="mono" href={href("actividades", task.external_id)}>
                          {task.external_id}
                        </a>{" "}
                        <span style={{ fontSize: 12.5 }}>{task.name}</span>
                      </td>
                      <td className="mono" style={{ fontSize: 12 }}>
                        {d(task.forecast_finish ?? task.finish)}
                      </td>
                      <td style={{ minWidth: 110 }}>
                        <Tag cls={statusTag(task.status)}>
                          {Math.round(task.progress)} % · {task.status_label}
                        </Tag>
                      </td>
                    </tr>
                  ))}
                  {!milestone.tasks.length && (
                    <tr>
                      <td colSpan={3} className="muted">
                        Sin tareas asociadas.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center" }}>
                <h4 className="h4" style={{ flex: 1 }}>
                  Criterios de aceptación
                </h4>
                {isManager && (
                  <button className="btn sm" onClick={() => setAdding(true)}>
                    <Icon name="plus" size={12} /> Criterio
                  </button>
                )}
              </div>
              {milestone.criteria.map((criterion) => (
                <CriterionRow key={criterion.id} criterion={criterion} onChanged={onChanged} />
              ))}
              {!milestone.criteria.length && <p className="muted">Este hito no tiene criterios.</p>}
              <p className="muted" style={{ fontSize: 12, marginBottom: 0 }}>
                El hito se marca cumplido (100 %) automáticamente cuando todos sus criterios están cumplidos, en la fecha de corte.
              </p>
            </div>
          </div>
        </div>
      )}
      {adding && <CriterionModal milestone={milestone} onClose={() => setAdding(false)} onDone={() => { setAdding(false); onChanged(); }} />}
    </section>
  );
}

function CriterionRow({ criterion, onChanged }: { criterion: Criterion; onChanged: () => void }) {
  const { isManager } = useAuth();
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [notes, setNotes] = useState(criterion.notes ?? "");
  const [busy, setBusy] = useState(false);

  async function setStatus(status: string) {
    setBusy(true);
    try {
      const result = await api.post<{ milestone_acceptance: string }>(`/criteria/${criterion.id}/status`, { status, notes: notes || null });
      toast("ok", `${criterion.external_id}: ${CRITERION_LABEL[status]}${result.milestone_acceptance === "CUMPLIDO" ? " · el hito quedó cumplido" : ""}.`);
      onChanged();
    } catch (err) {
      toast("crit", errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function upload(file: File) {
    try {
      await api.upload(`/criteria/${criterion.id}/files`, file);
      toast("ok", `Evidencia ${file.name} adjuntada a ${criterion.external_id}.`);
      onChanged();
    } catch (err) {
      toast("crit", errorMessage(err));
    }
  }

  async function remove(id: string) {
    try {
      await api.del(`/evidences/${id}`);
      onChanged();
    } catch (err) {
      toast("crit", errorMessage(err));
    }
  }

  return (
    <div className="crit-row">
      <div style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
        <Tag cls={statusTag(criterion.status)}>{CRITERION_LABEL[criterion.status]}</Tag>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13 }}>{criterion.description}</div>
          <div className="sub muted">
            <span className="mono">{criterion.external_id}</span> · Verificación: {criterion.verification_method}
            {criterion.responsible && ` · Responsable: ${criterion.responsible}`}
          </div>
          {criterion.verified_by && (
            <div className="sub muted">
              Verificado por {criterion.verified_by} el {dt(criterion.verified_at)}
              {criterion.notes ? ` — ${criterion.notes}` : ""}
            </div>
          )}
        </div>
      </div>
      <div className="ev-list">
        {criterion.evidences.map((evidence) => (
          <span key={evidence.id} className="file-chip">
            <Icon name="file" size={12} />
            <button className="link" onClick={() => void downloadFile(`/evidences/${evidence.id}/file`, evidence.file_name).catch((err) => toast("crit", errorMessage(err)))}>
              {evidence.file_name}
            </button>
            <span className="muted">{fileSize(evidence.size)}</span>
            {isManager && (
              <button className="link danger" onClick={() => void remove(evidence.id)} aria-label="Eliminar evidencia">
                <Icon name="x" size={11} />
              </button>
            )}
          </span>
        ))}
        <button className="btn sm" onClick={() => input.current?.click()}>
          <Icon name="upload" size={12} /> Evidencia
        </button>
        <input
          ref={input}
          type="file"
          hidden
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void upload(file);
            event.target.value = "";
          }}
        />
      </div>
      {isManager && (
        <div className="crit-actions">
          <input value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Observación de la verificación (opcional)" />
          <button className="btn sm ok" disabled={busy || criterion.status === "CUMPLIDO"} onClick={() => void setStatus("CUMPLIDO")}>
            Cumplido
          </button>
          <button className="btn sm danger" disabled={busy || criterion.status === "NO_CUMPLIDO"} onClick={() => void setStatus("NO_CUMPLIDO")}>
            No cumplido
          </button>
          {criterion.status !== "PENDIENTE" && (
            <button className="btn sm" disabled={busy} onClick={() => void setStatus("PENDIENTE")}>
              Reabrir
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function CriterionModal({ milestone, onClose, onDone }: { milestone: Milestone; onClose: () => void; onDone: () => void }) {
  const { projectId } = useProject();
  const [description, setDescription] = useState("");
  const [method, setMethod] = useState("");
  const [responsible, setResponsible] = useState("");
  const [error, setError] = useState<string | null>(null);
  async function save() {
    try {
      await api.post(`/projects/${projectId}/milestones/${milestone.external_id}/criteria`, { description, verification_method: method, responsible: responsible || null });
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    }
  }
  return (
    <Modal
      title={`Nuevo criterio para ${milestone.external_id}`}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            Cancelar
          </button>
          <button className="btn pri" disabled={!description || !method} onClick={() => void save()}>
            Agregar
          </button>
        </>
      }
    >
      <Field label="Descripción (¿qué debe cumplirse?)">
        <textarea value={description} onChange={(event) => setDescription(event.target.value)} />
      </Field>
      <Field label="Forma de verificación">
        <input value={method} onChange={(event) => setMethod(event.target.value)} placeholder="Acta firmada, informe de pruebas…" />
      </Field>
      <Field label="Responsable">
        <input value={responsible} onChange={(event) => setResponsible(event.target.value)} />
      </Field>
      {error && <Alert level="crit">{error}</Alert>}
    </Modal>
  );
}
