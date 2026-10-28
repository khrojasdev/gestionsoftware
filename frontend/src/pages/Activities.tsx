import { useMemo, useState } from "react";

import { api, errorMessage } from "../api";
import { useAuth } from "../auth";
import { RecalcModal } from "../components/Recalc";
import { Alert, Bar, Card, ErrorBox, Field, Icon, Loading, PageHeader, Tag, useLoad, useToast } from "../components/ui";
import { d, money, statusTag } from "../format";
import { useProject } from "../project";
import { go, href } from "../router";
import type { DepType, GanttElement, GanttFull, RecalcResult, ResourcesOverview } from "../types";

const KIND_LABEL: Record<string, string> = { ETAPA: "Etapa", ACTIVIDAD: "Actividad", SUBACTIVIDAD: "Subactividad", HITO: "Hito" };
const DEP_HELP: Record<DepType, string> = {
  FS: "Fin → Inicio: la sucesora empieza cuando termina la predecesora",
  SS: "Inicio → Inicio: ambas empiezan juntas (más desfase)",
  FF: "Fin → Fin: la sucesora termina cuando termina la predecesora",
  SF: "Inicio → Fin: la sucesora termina cuando empieza la predecesora",
};

type Filter = "tareas" | "todo" | "criticas" | "atrasadas" | "mias";

export default function ActivitiesPage({ focus }: { focus: string | null }) {
  const { projectId, version, touch } = useProject();
  const { isManager, user } = useAuth();
  const { data, error, loading, reload } = useLoad(
    () => Promise.all([api.get<GanttFull>(`/projects/${projectId}/gantt/full`), api.get<ResourcesOverview>(`/projects/${projectId}/resources/overview`)]),
    [projectId, version],
  );
  const [filter, setFilter] = useState<Filter>(isManager ? "tareas" : "mias");
  const [query, setQuery] = useState("");
  const [stage, setStage] = useState("");
  const [selected, setSelected] = useState<string | null>(focus);
  const [result, setResult] = useState<{ title: string; result: RecalcResult } | null>(null);

  const [lastFocus, setLastFocus] = useState(focus);
  if (focus !== lastFocus) {
    setLastFocus(focus);
    if (focus) setSelected(focus);
  }

  const mine = useMemo(() => {
    const set = new Set<string>();
    data?.[1].resources.filter((resource) => resource.user_id === user?.id).forEach((resource) => resource.assignments.forEach((assignment) => set.add(assignment.external_id)));
    return set;
  }, [data, user]);

  if (loading && !data) return <Loading />;
  if (error || !data) return <ErrorBox error={error ?? "Sin datos"} onRetry={() => void reload()} />;
  const [gantt] = data;
  const byId = new Map(gantt.elements.map((element) => [element.external_id, element]));
  const stageOf = (element: GanttElement): string => {
    let current: GanttElement | undefined = element;
    while (current && current.kind !== "ETAPA") current = current.parent ? byId.get(current.parent) : undefined;
    return current?.external_id ?? "";
  };
  const stages = gantt.elements.filter((element) => element.kind === "ETAPA");
  const q = query.trim().toLowerCase();
  const rows = gantt.elements.filter((element) => {
    if (stage && stageOf(element) !== stage) return false;
    if (q && !`${element.external_id} ${element.name} ${element.resources.join(" ")}`.toLowerCase().includes(q)) return false;
    switch (filter) {
      case "tareas":
        return element.kind === "SUBACTIVIDAD" || element.kind === "HITO";
      case "criticas":
        return (element.kind === "SUBACTIVIDAD" || element.kind === "HITO") && element.is_critical;
      case "atrasadas":
        return element.kind === "SUBACTIVIDAD" && (element.status === "ATRASADA" || element.status === "EN_RIESGO");
      case "mias":
        return mine.has(element.external_id);
      default:
        return true;
    }
  });
  const current = selected ? byId.get(selected) ?? null : null;

  return (
    <>
      <PageHeader crumb="Planificación" title="Actividades y precedencias">
        <a className="btn" href={href("gantt")}>
          Ver en Carta Gantt <Icon name="arrow" size={14} />
        </a>
      </PageHeader>
      <div className="split">
        <Card bodyClass="card-b" className="tbl-card">
          <div className="toolbar">
            <input className="search" placeholder="Buscar por ID, nombre o recurso…" value={query} onChange={(event) => setQuery(event.target.value)} />
            <select className="search" style={{ minWidth: 160 }} value={stage} onChange={(event) => setStage(event.target.value)} aria-label="Etapa">
              <option value="">Todas las etapas</option>
              {stages.map((item) => (
                <option key={item.external_id} value={item.external_id}>
                  {item.external_id} · {item.name}
                </option>
              ))}
            </select>
            <div className="sp" />
            {(
              [
                ["mias", "Mis tareas"],
                ["tareas", "Subactividades e hitos"],
                ["criticas", "Ruta crítica"],
                ["atrasadas", "Atrasadas / desplazadas"],
                ["todo", "Jerarquía completa"],
              ] as [Filter, string][]
            ).map(([value, label]) => (
              <button key={value} className={`chip ${filter === value ? "on" : ""}`} onClick={() => setFilter(value)}>
                {label}
              </button>
            ))}
          </div>
          <div className="scroll" style={{ maxHeight: "calc(100vh - 250px)" }}>
            <table className="t act">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Nombre</th>
                  <th className="num">Dur.</th>
                  <th>Inicio</th>
                  <th>Término</th>
                  <th>Predecesoras</th>
                  <th>Avance</th>
                  <th>Estado</th>
                  <th className="num">Holgura</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((element) => (
                  <tr
                    key={element.id}
                    className={`${selected === element.external_id ? "sel" : ""} lvl${element.level} k-${element.kind}`}
                    onClick={() => setSelected(element.external_id)}
                    style={{ cursor: "pointer" }}
                  >
                    <td className="mono">
                      {element.is_critical && element.kind !== "ETAPA" && element.kind !== "ACTIVIDAD" && <span className="crit-dot" title="Ruta crítica" />}
                      {element.external_id}
                    </td>
                    <td className="nm" title={element.name} style={{ paddingLeft: filter === "todo" ? 10 + element.level * 14 : undefined }}>
                      {element.kind === "HITO" && <span className="diamond" />}
                      {element.name}
                    </td>
                    <td className="num mono">{element.duration_days ?? "—"}</td>
                    <td className="mono">{d(element.start)}</td>
                    <td className="mono">
                      {d(element.finish)}
                      {element.slip_days > 0 && element.forecast_finish !== element.finish && (
                        <div className="sub warn-txt" title="Término proyectado">
                          → {d(element.forecast_finish)}
                        </div>
                      )}
                    </td>
                    <td>
                      {element.predecessors.map((dep) => (
                        <span key={dep.id} className="dep" style={{ marginRight: 3 }}>
                          {dep.predecessor}
                          {dep.type !== "FS" ? dep.type : ""}
                          {dep.lag_days ? (dep.lag_days > 0 ? `+${dep.lag_days}` : dep.lag_days) : ""}
                        </span>
                      ))}
                    </td>
                    <td style={{ minWidth: 90 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <Bar value={element.progress} plan={element.planned_pct} cls={element.status === "ATRASADA" ? "late" : ""} />
                        <span className="mono" style={{ fontSize: 11 }}>
                          {Math.round(element.progress)}%
                        </span>
                      </div>
                    </td>
                    <td>
                      <Tag cls={statusTag(element.status)}>{element.status_label}</Tag>
                    </td>
                    <td className="num mono">{element.total_slack ?? "—"}</td>
                  </tr>
                ))}
                {!rows.length && (
                  <tr>
                    <td colSpan={9} className="empty">
                      {filter === "mias" ? "No tienes tareas asignadas en este proyecto." : "Sin elementos para el filtro."}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
        <div className="drawer">
          {current ? (
            <Editor
              key={current.id}
              element={current}
              gantt={gantt}
              canPlan={isManager}
              canProgress={isManager || mine.has(current.external_id)}
              onDone={(title, value) => {
                setResult({ title, result: value });
                touch();
              }}
            />
          ) : (
            <Card title="Editor">
              <p className="muted" style={{ margin: 0 }}>
                Selecciona una fila para ver su detalle, editar duración y precedencias {isManager ? "" : "(solo Jefe de Proyecto) "}o registrar avance real.
              </p>
              <div className="mini-dep" style={{ marginTop: 14, gridTemplateColumns: "1fr 1fr" }}>
                {(Object.keys(DEP_HELP) as DepType[]).map((type) => (
                  <div className="md" key={type}>
                    <b className="mono">{type}</b>
                    <DepGlyph type={type} />
                    <span className="muted">{DEP_HELP[type]}</span>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      </div>
      {result && <RecalcModal title={result.title} result={result.result} onClose={() => setResult(null)} />}
    </>
  );
}

function DepGlyph({ type }: { type: DepType }) {
  const fromEnd = type === "FS" || type === "FF";
  const toEnd = type === "FF" || type === "SF";
  const ax = fromEnd ? 70 : 10;
  const bx = toEnd ? (type === "SF" ? 60 : 110) : type === "SS" ? 30 : 80;
  const barB = type === "SF" ? [0, 60] : type === "FF" ? [50, 110] : type === "SS" ? [30, 90] : [80, 130];
  return (
    <svg width="140" height="34" viewBox="0 0 140 34" aria-hidden="true">
      <rect x="10" y="3" width="60" height="9" rx="2" fill="#2e7d6b" />
      <rect x={barB[0]} y="22" width={barB[1] - barB[0]} height="9" rx="2" fill="#8a9198" />
      <path d={`M${ax} 12 V17 H${bx} V22`} stroke="#d96a17" fill="none" strokeWidth="1.5" />
    </svg>
  );
}

function Editor({
  element,
  gantt,
  canPlan,
  canProgress,
  onDone,
}: {
  element: GanttElement;
  gantt: GanttFull;
  canPlan: boolean;
  canProgress: boolean;
  onDone: (title: string, result: RecalcResult) => void;
}) {
  const toast = useToast();
  const { projectId } = useProject();
  const isLeaf = element.kind === "SUBACTIVIDAD" || element.kind === "HITO";
  const [name, setName] = useState(element.name);
  const [duration, setDuration] = useState(String(element.duration_days ?? ""));
  const [progress, setProgress] = useState(String(Math.round(element.progress)));
  const [actualStart, setActualStart] = useState(element.actual_start ?? "");
  const [actualFinish, setActualFinish] = useState(element.actual_finish ?? "");
  const [actualCost, setActualCost] = useState(String(Math.round(element.actual_cost || 0)));
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newDep, setNewDep] = useState<{ predecessor: string; type: DepType; lag: string }>({ predecessor: "", type: "FS", lag: "0" });

  const candidates = gantt.elements.filter((item) => (item.kind === "SUBACTIVIDAD" || item.kind === "HITO") && item.external_id !== element.external_id);
  const successors = gantt.links.filter((link) => link.from === element.external_id);

  async function run(title: string, action: () => Promise<RecalcResult>) {
    setBusy(true);
    setError(null);
    try {
      const value = await action();
      onDone(title, value);
    } catch (err) {
      setError(errorMessage(err));
      toast("crit", errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function savePlan() {
    const payload: Record<string, unknown> = {};
    if (name !== element.name) payload.name = name;
    if (element.kind === "SUBACTIVIDAD" && Number(duration) !== element.duration_days) payload.duration_days = Number(duration);
    if (!Object.keys(payload).length) return;
    void run(
      payload.duration_days !== undefined ? `${element.external_id}: duración ${element.duration_days} → ${duration} días` : `${element.external_id} actualizado`,
      () => api.patch<RecalcResult>(`/projects/${projectId}/elements/${element.external_id}`, payload),
    );
  }

  function saveProgress() {
    const payload: Record<string, unknown> = { progress_pct: Number(progress) };
    if (actualStart) payload.actual_start = actualStart;
    if (actualFinish) payload.actual_finish = actualFinish;
    if (element.kind === "SUBACTIVIDAD" && actualCost !== "") payload.actual_cost = Number(actualCost);
    if (notes) payload.notes = notes;
    void run(`${element.external_id}: avance registrado (${progress} %)`, () => api.patch<RecalcResult>(`/projects/${projectId}/elements/${element.external_id}`, payload));
  }

  return (
    <div className="grid">
      <Card
        title={
          <>
            <span className="mono muted">{element.external_id}</span> {KIND_LABEL[element.kind]}
          </>
        }
        actions={<Tag cls={statusTag(element.status)}>{element.status_label}</Tag>}
      >
        <p style={{ margin: "0 0 10px", fontWeight: 500 }}>{element.name}</p>
        <dl className="kv" style={{ gridTemplateColumns: "120px 1fr", fontSize: 12.5 }}>
          <dt>Plan</dt>
          <dd className="mono">
            {d(element.start)} → {d(element.finish)}
          </dd>
          <dt>Línea base</dt>
          <dd className="mono">
            {d(element.baseline_start)} → {d(element.baseline_finish)}
          </dd>
          <dt>Proyección</dt>
          <dd className="mono">
            {d(element.forecast_start)} → {d(element.forecast_finish)}
            {element.slip_days > 0 && <Tag cls="t-warn">+{element.slip_days} d</Tag>}
          </dd>
          <dt>Avance</dt>
          <dd>
            {Math.round(element.progress)} % real · {Math.round(element.planned_pct)} % planificado
          </dd>
          <dt>Costo</dt>
          <dd className="mono">
            {money(element.planned_cost)} plan · {money(element.actual_cost)} real
          </dd>
          <dt>Holgura</dt>
          <dd>
            {element.total_slack ?? "—"} días {element.is_critical && <Tag cls="t-crit">Ruta crítica</Tag>}
          </dd>
          {element.resources.length > 0 && (
            <>
              <dt>Recursos</dt>
              <dd>
                <a href={href("recursos", element.external_id)}>{element.resources.join(", ")}</a>
              </dd>
            </>
          )}
        </dl>
        {element.kind === "HITO" && (
          <p style={{ fontSize: 12.5, marginBottom: 0 }}>
            <a href={href("hitos", element.external_id)}>Ver criterios de aceptación del hito →</a>
          </p>
        )}
      </Card>

      {canPlan && (element.kind === "SUBACTIVIDAD" || element.kind === "ETAPA" || element.kind === "ACTIVIDAD") && (
        <Card title="Planificación">
          <Field label="Nombre">
            <input value={name} onChange={(event) => setName(event.target.value)} />
          </Field>
          {element.kind === "SUBACTIVIDAD" ? (
            <Field label="Duración (días hábiles)" hint="Al guardar se recalculan sucesoras, ruta crítica, costos y KPI.">
              <input type="number" min={1} value={duration} onChange={(event) => setDuration(event.target.value)} />
            </Field>
          ) : (
            <p className="muted" style={{ fontSize: 12 }}>
              Fechas, duración y costo de {KIND_LABEL[element.kind].toLowerCase()}s se consolidan desde sus subactividades.
            </p>
          )}
          <button className="btn pri" disabled={busy} onClick={savePlan}>
            {busy ? "Recalculando…" : "Guardar y recalcular"}
          </button>
        </Card>
      )}

      {isLeaf && (
        <Card title={`Precedencias (${element.predecessors.length})`}>
          {element.predecessors.map((dep) => (
            <DependencyRow key={dep.id} dep={dep} successor={element.external_id} canEdit={canPlan} onSaved={(title, value) => onDone(title, value)} />
          ))}
          {!element.predecessors.length && <p className="muted" style={{ margin: "0 0 8px", fontSize: 12.5 }}>Sin predecesoras: inicia con el proyecto.</p>}
          {canPlan && (
            <div className="dep-add">
              <select value={newDep.predecessor} onChange={(event) => setNewDep({ ...newDep, predecessor: event.target.value })} aria-label="Nueva predecesora">
                <option value="">+ Agregar predecesora…</option>
                {candidates.map((item) => (
                  <option key={item.external_id} value={item.external_id}>
                    {item.external_id} · {item.name.slice(0, 48)}
                  </option>
                ))}
              </select>
              <select value={newDep.type} onChange={(event) => setNewDep({ ...newDep, type: event.target.value as DepType })} aria-label="Tipo">
                {(["FS", "SS", "FF", "SF"] as DepType[]).map((type) => (
                  <option key={type} value={type} title={DEP_HELP[type]}>
                    {type}
                  </option>
                ))}
              </select>
              <input type="number" value={newDep.lag} onChange={(event) => setNewDep({ ...newDep, lag: event.target.value })} aria-label="Desfase" title="Desfase en días hábiles" />
              <button
                className="btn sm dark"
                disabled={!newDep.predecessor || busy}
                onClick={() =>
                  void run(`Precedencia ${newDep.predecessor} → ${element.external_id} (${newDep.type})`, () =>
                    api.post<RecalcResult>(`/projects/${projectId}/dependencies`, {
                      predecessor: newDep.predecessor,
                      successor: element.external_id,
                      type: newDep.type,
                      lag_days: Number(newDep.lag) || 0,
                    }),
                  )
                }
              >
                Agregar
              </button>
            </div>
          )}
          {successors.length > 0 && (
            <p className="muted" style={{ fontSize: 12, marginBottom: 0 }}>
              Sucesoras:{" "}
              {successors.map((link) => (
                <a key={link.id} className="dep" style={{ marginRight: 3 }} href={href("actividades", link.to)}>
                  {link.to}
                  {link.type !== "FS" ? link.type : ""}
                </a>
              ))}
            </p>
          )}
        </Card>
      )}

      {isLeaf && (
        <Card title="Avance real">
          {canProgress ? (
            <>
              <div className="row">
                <Field label="Avance (%)">
                  <input type="number" min={0} max={100} value={progress} onChange={(event) => setProgress(event.target.value)} />
                </Field>
                {element.kind === "SUBACTIVIDAD" && (
                  <Field label="Costo real (CLP)">
                    <input type="number" min={0} value={actualCost} onChange={(event) => setActualCost(event.target.value)} />
                  </Field>
                )}
              </div>
              <div className="row">
                <Field label="Inicio real">
                  <input type="date" value={actualStart} onChange={(event) => setActualStart(event.target.value)} />
                </Field>
                <Field label="Término real">
                  <input type="date" value={actualFinish} onChange={(event) => setActualFinish(event.target.value)} />
                </Field>
              </div>
              <Field label="Comentario">
                <input value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Opcional" />
              </Field>
              {element.kind === "HITO" && <p className="muted" style={{ fontSize: 12 }}>Un hito llega a 100 % solo cuando todos sus criterios de aceptación están cumplidos.</p>}
              <button className="btn ok" disabled={busy} onClick={saveProgress}>
                Registrar avance
              </button>
            </>
          ) : (
            <p className="muted" style={{ margin: 0, fontSize: 12.5 }}>
              Solo el Jefe de Proyecto o los integrantes asignados a esta tarea pueden registrar avance.
            </p>
          )}
        </Card>
      )}
      {error && <Alert level="crit">{error}</Alert>}
      <button className="btn sm" onClick={() => go("gantt", element.external_id)}>
        Ubicar en la Carta Gantt <Icon name="arrow" size={13} />
      </button>
    </div>
  );
}

function DependencyRow({
  dep,
  successor,
  canEdit,
  onSaved,
}: {
  dep: GanttElement["predecessors"][number];
  successor: string;
  canEdit: boolean;
  onSaved: (title: string, result: RecalcResult) => void;
}) {
  const { projectId } = useProject();
  const toast = useToast();
  const [type, setType] = useState<DepType>(dep.type);
  const [lag, setLag] = useState(String(dep.lag_days));
  const dirty = type !== dep.type || Number(lag) !== dep.lag_days;

  async function act(kind: "save" | "delete") {
    try {
      const result =
        kind === "save"
          ? await api.patch<RecalcResult>(`/projects/${projectId}/dependencies/${dep.id}`, { predecessor: dep.predecessor, successor, type, lag_days: Number(lag) || 0 })
          : await api.del<RecalcResult>(`/projects/${projectId}/dependencies/${dep.id}`);
      onSaved(kind === "save" ? `Precedencia ${dep.predecessor} → ${successor} actualizada (${type})` : `Precedencia ${dep.predecessor} → ${successor} eliminada`, result);
    } catch (err) {
      toast("crit", errorMessage(err));
    }
  }

  return (
    <div className="dep-row">
      <a className="dep" href={href("actividades", dep.predecessor)}>
        {dep.predecessor}
      </a>
      {canEdit ? (
        <>
          <select value={type} onChange={(event) => setType(event.target.value as DepType)} aria-label="Tipo de precedencia">
            {(["FS", "SS", "FF", "SF"] as DepType[]).map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
          <input type="number" value={lag} onChange={(event) => setLag(event.target.value)} aria-label="Desfase (días)" />
          <span className="muted" style={{ fontSize: 11 }}>
            días
          </span>
          <div className="sp" style={{ flex: 1 }} />
          {dirty && (
            <button className="btn sm dark" onClick={() => void act("save")}>
              Guardar
            </button>
          )}
          <button className="btn sm danger" onClick={() => void act("delete")} title="Eliminar precedencia">
            <Icon name="x" size={12} />
          </button>
        </>
      ) : (
        <span className="mono" style={{ fontSize: 12 }}>
          {dep.type} {dep.lag_days ? `${dep.lag_days > 0 ? "+" : ""}${dep.lag_days} d` : ""}
        </span>
      )}
    </div>
  );
}
