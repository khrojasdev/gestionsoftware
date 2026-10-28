import { useState } from "react";

import { api, errorMessage } from "../api";
import { Alert, Card, ErrorBox, Field, Icon, Loading, Modal, PageHeader, Tag, useLoad, useToast } from "../components/ui";
import { dt, moneyM, signed, statusTag } from "../format";
import { useProject } from "../project";
import { go, href } from "../router";
import type { ChangeBoard } from "../types";

const TYPES = [
  ["ALCANCE", "Alcance"],
  ["PLAZO", "Plazo"],
  ["COSTO", "Costo"],
  ["RECURSOS", "Recursos"],
];
const PRIORITIES = [
  ["BAJA", "Baja"],
  ["MEDIA", "Media"],
  ["ALTA", "Alta"],
  ["CRITICA", "Crítica"],
];
const PRIORITY_TAG: Record<string, string> = { BAJA: "t-mute", MEDIA: "t-info", ALTA: "t-warn", CRITICA: "t-crit" };

export default function ChangesPage() {
  const { projectId, version } = useProject();
  const { data, error, loading, reload } = useLoad(() => api.get<ChangeBoard>(`/projects/${projectId}/change-board`), [projectId, version]);
  const [status, setStatus] = useState("");
  const [type, setType] = useState("");
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);

  if (loading && !data) return <Loading />;
  if (error || !data) return <ErrorBox error={error ?? "Sin datos"} onRetry={() => void reload()} />;
  const q = query.trim().toLowerCase();
  const rows = data.requests.filter(
    (item) => (!status || item.status === status) && (!type || item.type === type) && (!q || `${item.code} ${item.title} ${item.requester_area ?? ""}`.toLowerCase().includes(q)),
  );
  const open = data.requests.filter((item) => item.status === "ABIERTA" || item.status === "APROBADA");

  return (
    <>
      <PageHeader crumb="Control" title="Solicitudes de cambio">
        <button className="btn pri" onClick={() => setCreating(true)}>
          <Icon name="plus" size={14} /> Nueva solicitud
        </button>
      </PageHeader>
      <div className="grid g4" style={{ marginBottom: 16 }}>
        <div className="card kpi">
          <div className="l">Solicitudes</div>
          <div className="v">{data.requests.length}</div>
          <div className="s">{open.length} en curso</div>
        </div>
        <div className="card kpi">
          <div className="l">
            <span className="dot d-ok" /> Aprobadas / cerradas
          </div>
          <div className="v">{data.requests.filter((item) => item.status === "APROBADA" || item.status === "CERRADA").length}</div>
          <div className="s">{data.requests.filter((item) => item.applied).length} aplicadas a la línea base</div>
        </div>
        <div className="card kpi">
          <div className="l">
            <span className="dot d-crit" /> Rechazadas
          </div>
          <div className="v">{data.requests.filter((item) => item.status === "RECHAZADA").length}</div>
        </div>
        <div className="card kpi">
          <div className="l">
            <span className={`dot ${data.requests.some((item) => item.sla_breached) ? "d-crit" : "d-ok"}`} /> Fuera de SLA
          </div>
          <div className="v">{data.requests.filter((item) => item.sla_breached).length}</div>
          <div className="s">en la etapa activa</div>
        </div>
      </div>
      <Card bodyClass="card-b scroll">
        <div className="toolbar">
          <input className="search" placeholder="Buscar por código, título o área…" value={query} onChange={(event) => setQuery(event.target.value)} />
          <select className="search" style={{ minWidth: 150 }} value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Estado">
            <option value="">Todos los estados</option>
            {["ABIERTA", "APROBADA", "RECHAZADA", "CERRADA", "CANCELADA"].map((value) => (
              <option key={value} value={value}>
                {value[0] + value.slice(1).toLowerCase()}
              </option>
            ))}
          </select>
          <select className="search" style={{ minWidth: 150 }} value={type} onChange={(event) => setType(event.target.value)} aria-label="Tipo">
            <option value="">Todos los tipos</option>
            {TYPES.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <table className="t">
          <thead>
            <tr>
              <th>Código</th>
              <th>Solicitud</th>
              <th>Tipo</th>
              <th>Prioridad</th>
              <th>Etapa actual</th>
              <th className="num">Impacto plazo</th>
              <th className="num">Impacto costo</th>
              <th className="num">Evid.</th>
              <th>Estado</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((item) => (
              <tr key={item.id} onClick={() => go("cambio", item.id)} style={{ cursor: "pointer" }}>
                <td className="mono">
                  <a href={href("cambio", item.id)}>{item.code}</a>
                </td>
                <td style={{ maxWidth: 340 }}>
                  <b style={{ fontWeight: 500 }}>{item.title}</b>
                  <div className="sub muted">
                    {item.requester_area ?? "—"} · {dt(item.created_at)}
                  </div>
                </td>
                <td>{item.type_label}</td>
                <td>
                  <Tag cls={PRIORITY_TAG[item.priority] ?? "t-mute"}>{item.priority[0] + item.priority.slice(1).toLowerCase()}</Tag>
                </td>
                <td style={{ minWidth: 190 }}>
                  <div className="mini-steps" title={`${item.stages_completed} de ${item.stages_total} etapas completadas`}>
                    {Array.from({ length: item.stages_total }, (_, index) => (
                      <i key={index} className={index < item.stages_completed ? "done" : index + 1 === item.stage_sequence && item.status === "ABIERTA" ? "cur" : item.status === "RECHAZADA" && index + 1 === item.stage_sequence ? "rej" : ""} />
                    ))}
                  </div>
                  <div className="sub">
                    {item.stage_sequence}. {item.stage_name} {item.sla_breached && <Tag cls="t-crit">SLA vencido</Tag>}
                  </div>
                </td>
                <td className="num mono">{item.delta_days !== null ? signed(item.delta_days, " d") : "—"}</td>
                <td className="num mono">{item.delta_cost !== null ? `${item.delta_cost > 0 ? "+" : ""}${moneyM(item.delta_cost)}` : "—"}</td>
                <td className="num mono">{item.evidences}</td>
                <td>
                  <Tag cls={statusTag(item.status)}>{item.status_label}</Tag>
                  {item.applied && <div className="sub muted">Aplicada</div>}
                </td>
              </tr>
            ))}
            {!rows.length && (
              <tr>
                <td colSpan={9} className="empty">
                  No hay solicitudes para el filtro.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>
      {creating && <CreateModal onClose={() => setCreating(false)} />}
    </>
  );
}

function CreateModal({ onClose }: { onClose: () => void }) {
  const { projectId, touch } = useProject();
  const toast = useToast();
  const [draft, setDraft] = useState({ title: "", description: "", justification: "", change_type: "ALCANCE", priority: "MEDIA", requester_area: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (key: keyof typeof draft) => (event: { target: { value: string } }) => setDraft((value) => ({ ...value, [key]: event.target.value }));

  async function save() {
    setBusy(true);
    try {
      const created = await api.post<{ id: string; code: string }>(`/projects/${projectId}/change-requests-v2`, {
        ...draft,
        justification: draft.justification || null,
        requester_area: draft.requester_area || null,
      });
      toast("ok", `Solicitud ${created.code} registrada en la etapa 1 (Registro).`);
      touch();
      go("cambio", created.id);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <Modal
      title="Nueva solicitud de cambio"
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            Cancelar
          </button>
          <button className="btn pri" disabled={busy || draft.title.length < 3 || draft.description.length < 3} onClick={() => void save()}>
            Registrar
          </button>
        </>
      }
    >
      <Field label="Título">
        <input value={draft.title} onChange={set("title")} placeholder="Qué se quiere cambiar" />
      </Field>
      <Field label="Descripción">
        <textarea value={draft.description} onChange={set("description")} />
      </Field>
      <Field label="Justificación (beneficio esperado)">
        <textarea value={draft.justification} onChange={set("justification")} />
      </Field>
      <div className="row">
        <Field label="Tipo">
          <select value={draft.change_type} onChange={set("change_type")}>
            {TYPES.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Prioridad">
          <select value={draft.priority} onChange={set("priority")}>
            {PRIORITIES.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Área solicitante">
          <input value={draft.requester_area} onChange={set("requester_area")} placeholder="Operaciones, Finanzas…" />
        </Field>
      </div>
      <p className="muted" style={{ fontSize: 12, margin: 0 }}>
        La solicitud recorre 10 etapas con SLA: registro, revisión inicial, clasificación, análisis de impacto, comité, decisión, planificación, implementación, verificación y cierre con nueva línea base.
      </p>
      {error && <Alert level="crit">{error}</Alert>}
    </Modal>
  );
}
