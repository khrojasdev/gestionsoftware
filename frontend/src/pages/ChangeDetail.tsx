import { useRef, useState } from "react";

import { api, downloadFile, errorMessage } from "../api";
import { useAuth } from "../auth";
import { Alert, Card, ErrorBox, Field, FinishShift, Icon, Loading, Modal, PageHeader, Tag, useLoad, useToast } from "../components/ui";
import { d, dt, fileSize, money, moneyM, n, pct, signed, signedMoney, statusTag } from "../format";
import { useProject } from "../project";
import { href } from "../router";
import type { ChangeDetail, ProjectFinish, ProposalItem, Simulation } from "../types";

const DECISION = 6;
const IMPLEMENTATION = 8;

type Applied = { baseline_version: string; finish_before: ProjectFinish | null; finish_after: ProjectFinish | null; kpis_recalculated: number; impact: Simulation };

export default function ChangeDetailPage({ id }: { id: string }) {
  const { touch, version } = useProject();
  const { isManager } = useAuth();
  const toast = useToast();
  const { data, error, loading, reload } = useLoad(() => api.get<ChangeDetail>(`/change-requests/${id}/detail`), [id, version]);
  const [simulation, setSimulation] = useState<Simulation | null>(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [applied, setApplied] = useState<Applied | null>(null);
  const [editing, setEditing] = useState(false);

  if (loading && !data) return <Loading />;
  if (error || !data) return <ErrorBox error={error ?? "Sin datos"} onRetry={() => void reload()} />;
  const { request } = data;
  const active = data.stages.find((stage) => stage.status === "ACTIVA") ?? null;
  const sim = simulation ?? data.preview;
  const isOpen = request.status === "ABIERTA";
  const isApproved = request.status === "APROBADA";
  const canApply = isManager && isApproved && !request.applied && active !== null && active.sequence <= IMPLEMENTATION;
  const canEditProposal = isManager && (isOpen || isApproved) && !request.applied;

  async function act(label: string, action: () => Promise<unknown>, after?: (value: unknown) => void) {
    setBusy(true);
    try {
      const value = await action();
      setComment("");
      after?.(value);
      toast("ok", label);
      touch();
    } catch (err) {
      toast("crit", errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader crumb="Control · Solicitudes de cambio" title={`${request.code} · ${request.title}`}>
        <a className="btn" href={href("cambios")}>
          ← Volver al listado
        </a>
      </PageHeader>
      <Card className="stepper-card">
        <div className="steps">
          {data.stages.map((stage) => {
            const rejected = request.status === "RECHAZADA" && stage.status === "COMPLETADA" && stage.sequence === request.stage_sequence;
            const cls = rejected ? "rej" : stage.status === "COMPLETADA" ? "done" : stage.status === "ACTIVA" ? "cur" : stage.status === "OMITIDA" ? "skip" : "";
            return (
              <div key={stage.sequence} className={`st ${cls}`} title={stage.notes ?? undefined}>
                {stage.name}
                <small className={stage.breached ? "warn-txt" : "muted"}>
                  {stage.elapsed_hours !== null ? `${n(stage.elapsed_hours, 1)} h` : ""}
                  {stage.sla_hours ? ` / SLA ${stage.sla_hours} h` : ""}
                </small>
              </div>
            );
          })}
        </div>
      </Card>
      <div className="split" style={{ marginTop: 16 }}>
        <div className="grid">
          <Card title="Solicitud" actions={<Tag cls={statusTag(request.status)}>{request.status_label}</Tag>}>
            <dl className="kv">
              <dt>Descripción</dt>
              <dd>{request.description}</dd>
              {request.justification && (
                <>
                  <dt>Justificación</dt>
                  <dd>{request.justification}</dd>
                </>
              )}
              <dt>Tipo · prioridad</dt>
              <dd>
                {request.type_label} · {request.priority[0] + request.priority.slice(1).toLowerCase()}
              </dd>
              <dt>Solicitante</dt>
              <dd>
                {request.requester ?? "—"} {request.requester_area && <span className="muted">({request.requester_area})</span>}
              </dd>
              <dt>Responsable</dt>
              <dd>{request.responsible ?? "—"}</dd>
              <dt>Registrada</dt>
              <dd className="mono">{dt(request.created_at)}</dd>
              {request.decided_at && (
                <>
                  <dt>Decisión</dt>
                  <dd className="mono">{dt(request.decided_at)}</dd>
                </>
              )}
              {request.closed_at && (
                <>
                  <dt>Cierre</dt>
                  <dd className="mono">{dt(request.closed_at)}</dd>
                </>
              )}
            </dl>
          </Card>

          <Card
            title="Propuesta de cambio sobre el plan"
            actions={
              canEditProposal && (
                <button className="btn sm" onClick={() => setEditing(true)}>
                  <Icon name="edit" size={12} /> Editar propuesta
                </button>
              )
            }
          >
            {data.proposal.length ? (
              <table className="t">
                <thead>
                  <tr>
                    <th>Tarea</th>
                    <th className="num">Duración propuesta</th>
                    <th>Recursos adicionales</th>
                    <th>Nota</th>
                  </tr>
                </thead>
                <tbody>
                  {data.proposal.map((item, index) => {
                    const task = data.tasks.find((row) => row.external_id === item.task_id);
                    return (
                      <tr key={index}>
                        <td>
                          <a className="mono" href={href("actividades", item.task_id)}>
                            {item.task_id}
                          </a>{" "}
                          <span style={{ fontSize: 12.5 }}>{task?.name}</span> {task?.is_critical && <Tag cls="t-crit">Crítica</Tag>}
                        </td>
                        <td className="num mono">{item.duration_days ? `${task?.duration_days ?? "?"} → ${item.duration_days} d` : "—"}</td>
                        <td style={{ fontSize: 12.5 }}>
                          {(item.resources ?? []).map((resource) => {
                            const row = data.resources.find((value) => value.external_id === resource.resource);
                            return (
                              <div key={resource.resource}>
                                <span className="mono">{resource.resource}</span> {row?.name} +{resource.hours ?? resource.quantity}
                                {resource.hours ? " h" : " u"} ({money((resource.hours ?? resource.quantity ?? 0) * (row?.rate ?? 0))})
                              </div>
                            );
                          })}
                          {!(item.resources ?? []).length && "—"}
                        </td>
                        <td style={{ fontSize: 12.5 }}>{item.note ?? ""}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : (
              <p className="muted" style={{ margin: 0 }}>
                Aún no se define qué tareas, duraciones o recursos cambiarían. {canEditProposal ? "Usa «Editar propuesta» para describirlo y luego simula el impacto." : ""}
              </p>
            )}
            {isManager && data.proposal.length > 0 && !request.applied && (isOpen || isApproved) && (
              <button className="btn dark" style={{ marginTop: 12 }} disabled={busy} onClick={() => void act("Impacto simulado sobre la línea base vigente.", () => api.post<Simulation>(`/change-requests/${id}/simulate`), (value) => setSimulation(value as Simulation))}>
                <Icon name="play" size={12} /> Simular impacto
              </button>
            )}
          </Card>

          {sim && <ImpactCard sim={sim} committed={data.committed_finish} title={request.applied ? "Impacto aplicado" : "Análisis de impacto (simulación sobre la línea base vigente)"} />}
          {!sim && data.impacts.length > 0 && (
            <Card title={request.applied ? "Impacto aplicado al plan" : "Impacto registrado"}>
              <p style={{ marginTop: 0 }}>
                <b>{data.impacts[0].summary}</b> <span className="muted">· evaluado el {dt(data.impacts[0].simulated_at)}</span>
              </p>
              {data.impacts[0].affected.length > 0 && (
                <div className="scroll" style={{ maxHeight: 260 }}>
                  <table className="t">
                    <thead>
                      <tr>
                        <th>Tarea</th>
                        <th>Término</th>
                        <th className="num">Duración</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.impacts[0].affected.map((row) => (
                        <tr key={row.task_id}>
                          <td>
                            <span className="mono">{row.task_id}</span> <span style={{ fontSize: 12.5 }}>{row.name}</span> {row.critical && <Tag cls="t-crit">Crítica</Tag>}
                          </td>
                          <td className="mono" style={{ fontSize: 12 }}>
                            {d(row.finish_before)} → <b>{d(row.finish_after)}</b>
                          </td>
                          <td className="num mono">{row.duration_before === row.duration_after ? row.duration_after : `${row.duration_before} → ${row.duration_after}`}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          )}

          <Evidences detail={data} onChanged={touch} />

          <Card title="Historial y trazabilidad">
            {data.transitions.map((item, index) => (
              <div className="ev" key={`t${index}`}>
                <span className="when">{dt(item.occurred_at)}</span>
                <div>
                  <b style={{ fontWeight: 500 }}>
                    {item.from_stage ? `${item.from_stage} → ` : ""}
                    {item.to_stage ?? (item.to_status === "RECHAZADA" ? "Rechazada" : item.to_status === "CERRADA" ? "Cerrada" : "—")}
                  </b>
                  {item.from_status !== item.to_status && item.to_status && <Tag cls={statusTag(item.to_status)}>{item.to_status.toLowerCase()}</Tag>}
                  <div className="sub muted">
                    {item.by ?? "Sistema"}
                    {item.comment ? ` — ${item.comment}` : ""}
                  </div>
                </div>
              </div>
            ))}
            <details style={{ marginTop: 8 }}>
              <summary className="muted" style={{ fontSize: 12.5, cursor: "pointer" }}>
                Registro de auditoría ({data.audit.length})
              </summary>
              {data.audit.map((item, index) => (
                <div className="ev" key={`a${index}`}>
                  <span className="when">{dt(item.occurred_at)}</span>
                  <div>
                    <span className="mono" style={{ fontSize: 12 }}>
                      {item.action}
                    </span>{" "}
                    <span className="muted">{item.by ?? "Sistema"}</span>
                    {item.data && <div className="sub mono muted ell" style={{ maxWidth: 520 }}>{JSON.stringify(item.data)}</div>}
                  </div>
                </div>
              ))}
            </details>
          </Card>
        </div>

        <div className="drawer grid">
          <Card title="Acción en la etapa actual">
            {request.status === "RECHAZADA" && <Alert level="crit">Solicitud rechazada en «{request.stage_name}». No modifica el plan.</Alert>}
            {request.status === "CERRADA" && <Alert level="ok">Solicitud cerrada. {request.applied ? "El cambio quedó incorporado en una nueva línea base." : ""}</Alert>}
            {active && (
              <>
                <p style={{ margin: "0 0 4px" }}>
                  Etapa <b>{active.sequence}. {active.name}</b>
                </p>
                <p className="muted" style={{ margin: "0 0 10px", fontSize: 12.5 }}>
                  En la etapa desde {dt(active.entered_at)} · {n(active.elapsed_hours ?? 0, 1)} h de {active.sla_hours ?? "—"} h de SLA{" "}
                  {active.breached && <Tag cls="t-crit">SLA vencido</Tag>}
                </p>
                {!isManager && <Alert level="info">Solo el Jefe de Proyecto o el Administrador hacen avanzar, aprueban o aplican solicitudes. Puedes adjuntar evidencias.</Alert>}
                {isManager && (
                  <>
                    <Field label="Comentario de la etapa">
                      <textarea value={comment} onChange={(event) => setComment(event.target.value)} rows={2} placeholder="Acuerdo, revisión realizada, observaciones…" />
                    </Field>
                    {isOpen && active.sequence === DECISION && (
                      <div style={{ display: "flex", gap: 8 }}>
                        <button className="btn ok" disabled={busy} onClick={() => void act(`${request.code} aprobada. Siguiente: planificar e implementar el cambio.`, () => api.post(`/change-requests/${id}/decision`, { approve: true, comment: comment || null }))}>
                          Aprobar
                        </button>
                        <button className="btn danger" disabled={busy} onClick={() => void act(`${request.code} rechazada.`, () => api.post(`/change-requests/${id}/decision`, { approve: false, comment: comment || null }))}>
                          Rechazar
                        </button>
                      </div>
                    )}
                    {isOpen && active.sequence !== DECISION && (
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                        <button className="btn dark" disabled={busy} onClick={() => void act(`${request.code} avanzó a la etapa ${active.sequence + 1}.`, () => api.post(`/change-requests/${id}/advance`, { comment: comment || null }))}>
                          Avanzar a «{data.stages[active.sequence]?.name}»
                        </button>
                        <button className="btn danger" disabled={busy} onClick={() => void act(`${request.code} rechazada.`, () => api.post(`/change-requests/${id}/decision`, { approve: false, comment: comment || null }))}>
                          Rechazar
                        </button>
                      </div>
                    )}
                    {canApply && (
                      <>
                        <button
                          className="btn pri"
                          style={{ width: "100%", justifyContent: "center", marginTop: 8 }}
                          disabled={busy || !data.proposal.length}
                          onClick={() => void act(`${request.code} aplicada: nueva línea base generada.`, () => api.post<Applied>(`/change-requests/${id}/apply-v2`), (value) => setApplied(value as Applied))}
                        >
                          Aplicar cambio al plan y generar nueva línea base
                        </button>
                        {!data.proposal.length && <p className="muted" style={{ fontSize: 12 }}>Define la propuesta antes de aplicar.</p>}
                      </>
                    )}
                    {isApproved && !canApply && (
                      <button className="btn dark" disabled={busy} onClick={() => void act(active.sequence === 10 ? `${request.code} cerrada.` : `${request.code} avanzó a la etapa ${active.sequence + 1}.`, () => api.post(`/change-requests/${id}/advance`, { comment: comment || null }))}>
                        {active.sequence === 10 ? "Cerrar solicitud" : `Avanzar a «${data.stages[active.sequence]?.name}»`}
                      </button>
                    )}
                    {isApproved && canApply && active.sequence < IMPLEMENTATION && (
                      <p className="muted" style={{ fontSize: 12, marginBottom: 0 }}>
                        Al aplicar, el sistema completa Planificación e Implementación, recalcula el Gantt, costos y KPI y congela la línea base siguiente.
                      </p>
                    )}
                  </>
                )}
              </>
            )}
          </Card>
          <Card title="Contingencia del proyecto">
            <dl className="kv" style={{ gridTemplateColumns: "130px 1fr" }}>
              <dt>Reserva de contingencia</dt>
              <dd className="mono">{money(data.contingency_amount)}</dd>
              {sim && (
                <>
                  <dt>Consumo de este cambio</dt>
                  <dd className="mono">
                    {money(sim.delta_contingency)} ({pct(sim.contingency_consumption_pct, 1)})
                  </dd>
                </>
              )}
              <dt>Término comprometido</dt>
              <dd className="mono">{d(data.committed_finish)}</dd>
            </dl>
          </Card>
          <Card title="Guía del flujo (10 etapas)">
            <ol className="flow-list">
              {data.stages.map((stage) => (
                <li key={stage.sequence} className={stage.status === "ACTIVA" ? "cur" : stage.status === "COMPLETADA" ? "done" : ""}>
                  {stage.name}
                  {stage.completed_by && <span className="muted"> · {stage.completed_by}</span>}
                </li>
              ))}
            </ol>
          </Card>
        </div>
      </div>
      {editing && <ProposalModal detail={data} onClose={() => setEditing(false)} onSaved={() => { setEditing(false); setSimulation(null); touch(); }} />}
      {applied && (
        <Modal
          wide
          title={`Cambio aplicado · línea base ${applied.baseline_version}`}
          onClose={() => setApplied(null)}
          footer={
            <>
              <a className="btn" href={href("gantt")} onClick={() => setApplied(null)}>
                Ver Carta Gantt
              </a>
              <a className="btn" href={href("tablero-cambio")} onClick={() => setApplied(null)}>
                Ver tablero del cambio
              </a>
              <button className="btn dark" onClick={() => setApplied(null)}>
                Entendido
              </button>
            </>
          }
        >
          <div className="recalc-head">
            <div>
              <b>{applied.baseline_version}</b>
              <span>nueva línea base</span>
            </div>
            <div>
              <b>{applied.kpis_recalculated}</b>
              <span>KPI recalculados</span>
            </div>
            <div className="grow">
              <FinishShift before={applied.finish_before} after={applied.finish_after} />
            </div>
          </div>
          <ImpactBody sim={applied.impact} committed={data.committed_finish} />
        </Modal>
      )}
    </>
  );
}

function ImpactCard({ sim, committed, title }: { sim: Simulation; committed: string | null; title: string }) {
  return (
    <Card title={title}>
      <ImpactBody sim={sim} committed={committed} />
    </Card>
  );
}

function ImpactBody({ sim, committed }: { sim: Simulation; committed: string | null }) {
  const reserveLevel = sim.reserve_after === null ? "info" : sim.reserve_after < 0 ? "crit" : sim.reserve_after < 10 ? "warn" : "ok";
  return (
    <>
      <div className="grid g4" style={{ marginBottom: 12 }}>
        <div className="impact">
          <span>Término del proyecto</span>
          <b className="mono">{d(sim.proposed_finish)}</b>
          <small>
            base {d(sim.baseline_finish)} · {signed(sim.delta_schedule_days, " días hábiles")}
          </small>
        </div>
        <div className="impact">
          <span>Costo total</span>
          <b className="mono">{moneyM(sim.proposed_cost)}</b>
          <small>
            base {moneyM(sim.baseline_cost)} · {signedMoney(sim.delta_cost)}
          </small>
        </div>
        <div className={`impact ${(sim.contingency_consumption_pct ?? 0) > 25 ? "warn" : ""}`}>
          <span>Contingencia consumida</span>
          <b className="mono">{pct(sim.contingency_consumption_pct, 1)}</b>
          <small>de {moneyM(sim.contingency_amount)}</small>
        </div>
        <div className={`impact ${reserveLevel}`}>
          <span>Reserva de plazo</span>
          <b className="mono">
            {sim.reserve_before ?? "—"} → {sim.reserve_after ?? "—"} d
          </b>
          <small>hábiles hasta el {d(committed)}</small>
        </div>
      </div>
      {sim.critical_affected && <Alert level="warn">El cambio afecta la ruta crítica: desplaza el término del proyecto.</Alert>}
      {sim.reserve_after !== null && sim.reserve_after < 0 && <Alert level="crit">El término propuesto supera la fecha comprometida con el cliente.</Alert>}
      {sim.resources.length > 0 && (
        <>
          <h4 className="h4" style={{ marginTop: 12 }}>
            Efecto en recursos
          </h4>
          <table className="t">
            <thead>
              <tr>
                <th>Recurso</th>
                <th className="num">Antes</th>
                <th className="num">Después</th>
                <th className="num">Diferencia</th>
              </tr>
            </thead>
            <tbody>
              {sim.resources.map((row) => (
                <tr key={row.resource}>
                  <td>{row.resource}</td>
                  <td className="num mono">{n(row.before, 1)}</td>
                  <td className="num mono">{n(row.after, 1)}</td>
                  <td className="num mono">{signed(row.delta)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      <h4 className="h4" style={{ marginTop: 12 }}>
        Tareas afectadas ({sim.affected.length})
      </h4>
      <div className="scroll" style={{ maxHeight: 300 }}>
        <table className="t">
          <thead>
            <tr>
              <th>Tarea</th>
              <th>Término</th>
              <th className="num">Duración</th>
              <th className="num">Costo</th>
            </tr>
          </thead>
          <tbody>
            {sim.affected.map((row) => (
              <tr key={row.task_id}>
                <td>
                  <span className="mono">{row.task_id}</span> <span style={{ fontSize: 12.5 }}>{row.name}</span> {row.critical && <Tag cls="t-crit">Crítica</Tag>}
                </td>
                <td className="mono" style={{ fontSize: 12 }}>
                  {d(row.finish_before)} → <b>{d(row.finish_after)}</b>
                </td>
                <td className="num mono">
                  {row.duration_before === row.duration_after ? row.duration_after : `${row.duration_before} → ${row.duration_after}`}
                </td>
                <td className="num mono">{row.cost_before === row.cost_after ? money(row.cost_after) : `${money(row.cost_before)} → ${money(row.cost_after)}`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted" style={{ fontSize: 12, marginBottom: 0 }}>{sim.summary}</p>
    </>
  );
}

function Evidences({ detail, onChanged }: { detail: ChangeDetail; onChanged: () => void }) {
  const { isManager } = useAuth();
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  async function upload(file: File) {
    try {
      await api.upload(`/change-requests/${detail.request.id}/files`, file);
      toast("ok", `Evidencia ${file.name} adjuntada.`);
      onChanged();
    } catch (err) {
      toast("crit", errorMessage(err));
    }
  }
  return (
    <Card
      title={`Evidencias (${detail.evidences.length})`}
      actions={
        <>
          <button className="btn sm" onClick={() => input.current?.click()}>
            <Icon name="upload" size={12} /> Adjuntar
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
        </>
      }
    >
      {!detail.evidences.length && <Alert level="warn">La solicitud no tiene evidencias; el KPI C08 la cuenta como incompleta.</Alert>}
      {detail.evidences.map((evidence) => (
        <div className="file" key={evidence.id} style={{ marginBottom: 8 }}>
          <div className="xls" style={{ background: "#5a6570" }}>
            {evidence.file_name.split(".").pop()?.toUpperCase().slice(0, 4)}
          </div>
          <div style={{ flex: 1 }}>
            <button className="link" onClick={() => void downloadFile(`/evidences/${evidence.id}/file`, evidence.file_name).catch((err) => toast("crit", errorMessage(err)))}>
              {evidence.file_name}
            </button>
            <div className="muted" style={{ fontSize: 12 }}>
              {fileSize(evidence.size)} · {evidence.uploaded_by ?? "—"} · {dt(evidence.uploaded_at)}
            </div>
          </div>
          {isManager && (
            <button
              className="btn sm danger"
              onClick={async () => {
                try {
                  await api.del(`/evidences/${evidence.id}`);
                  onChanged();
                } catch (err) {
                  toast("crit", errorMessage(err));
                }
              }}
              aria-label="Eliminar evidencia"
            >
              <Icon name="trash" size={12} />
            </button>
          )}
        </div>
      ))}
    </Card>
  );
}

type DraftItem = { task_id: string; duration_days: string; note: string; resources: { resource: string; amount: string }[] };

function ProposalModal({ detail, onClose, onSaved }: { detail: ChangeDetail; onClose: () => void; onSaved: () => void }) {
  const [items, setItems] = useState<DraftItem[]>(
    detail.proposal.length
      ? detail.proposal.map((item) => ({
          task_id: item.task_id,
          duration_days: item.duration_days ? String(item.duration_days) : "",
          note: item.note ?? "",
          resources: (item.resources ?? []).map((resource) => ({ resource: resource.resource, amount: String(resource.hours ?? resource.quantity ?? "") })),
        }))
      : [{ task_id: "", duration_days: "", note: "", resources: [] }],
  );
  const [error, setError] = useState<string | null>(null);

  function update(index: number, patch: Partial<DraftItem>) {
    setItems((list) => list.map((item, position) => (position === index ? { ...item, ...patch } : item)));
  }

  async function save() {
    const updates: ProposalItem[] = items
      .filter((item) => item.task_id)
      .map((item) => {
        const value: ProposalItem = { task_id: item.task_id };
        if (item.duration_days) value.duration_days = Number(item.duration_days);
        if (item.note) value.note = item.note;
        const resources = item.resources
          .filter((resource) => resource.resource && Number(resource.amount) > 0)
          .map((resource) => {
            const row = detail.resources.find((r) => r.external_id === resource.resource);
            return row?.type === "HUMANO" ? { resource: resource.resource, hours: Number(resource.amount) } : { resource: resource.resource, quantity: Number(resource.amount) };
          });
        if (resources.length) value.resources = resources;
        return value;
      });
    try {
      await api.put(`/change-requests/${detail.request.id}/proposal`, { updates });
      onSaved();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <Modal
      wide
      title={`Propuesta de ${detail.request.code}`}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={() => setItems((list) => [...list, { task_id: "", duration_days: "", note: "", resources: [] }])}>
            <Icon name="plus" size={12} /> Otra tarea
          </button>
          <div style={{ flex: 1 }} />
          <button className="btn" onClick={onClose}>
            Cancelar
          </button>
          <button className="btn pri" onClick={() => void save()}>
            Guardar propuesta
          </button>
        </>
      }
    >
      <p className="muted" style={{ marginTop: 0, fontSize: 12.5 }}>
        Indica qué subactividades cambian: nueva duración y/o recursos adicionales (horas para profesionales, cantidad para recursos no humanos). Después usa «Simular impacto».
      </p>
      {items.map((item, index) => {
        const task = detail.tasks.find((row) => row.external_id === item.task_id);
        return (
          <div key={index} className="prop-item">
            <div className="row">
              <Field label="Tarea">
                <select value={item.task_id} onChange={(event) => update(index, { task_id: event.target.value })}>
                  <option value="">Selecciona…</option>
                  {detail.tasks.map((row) => (
                    <option key={row.external_id} value={row.external_id}>
                      {row.external_id} · {row.name.slice(0, 60)} ({row.duration_days} d)
                    </option>
                  ))}
                </select>
              </Field>
              <Field label={`Nueva duración${task ? ` (actual ${task.duration_days} d)` : ""}`}>
                <input type="number" min={1} value={item.duration_days} onChange={(event) => update(index, { duration_days: event.target.value })} placeholder="Sin cambio" />
              </Field>
            </div>
            {item.resources.map((resource, rIndex) => (
              <div className="row" key={rIndex} style={{ alignItems: "flex-end" }}>
                <Field label="Recurso adicional">
                  <select
                    value={resource.resource}
                    onChange={(event) => update(index, { resources: item.resources.map((value, position) => (position === rIndex ? { ...value, resource: event.target.value } : value)) })}
                  >
                    <option value="">Selecciona…</option>
                    {detail.resources.map((row) => (
                      <option key={row.external_id} value={row.external_id}>
                        {row.external_id} · {row.name} ({money(row.rate)})
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Horas / cantidad adicional">
                  <input
                    type="number"
                    min={0}
                    value={resource.amount}
                    onChange={(event) => update(index, { resources: item.resources.map((value, position) => (position === rIndex ? { ...value, amount: event.target.value } : value)) })}
                  />
                </Field>
                <button className="btn sm danger" style={{ flex: "none", marginBottom: 12 }} onClick={() => update(index, { resources: item.resources.filter((_, position) => position !== rIndex) })}>
                  <Icon name="x" size={12} />
                </button>
              </div>
            ))}
            <div className="row" style={{ alignItems: "flex-end" }}>
              <Field label="Nota">
                <input value={item.note} onChange={(event) => update(index, { note: event.target.value })} />
              </Field>
              <button className="btn sm" style={{ flex: "none", marginBottom: 12 }} onClick={() => update(index, { resources: [...item.resources, { resource: "", amount: "" }] })}>
                + Recurso
              </button>
              <button className="btn sm danger" style={{ flex: "none", marginBottom: 12 }} onClick={() => setItems((list) => list.filter((_, position) => position !== index))}>
                Quitar tarea
              </button>
            </div>
          </div>
        );
      })}
      {error && <Alert level="crit">{error}</Alert>}
    </Modal>
  );
}
