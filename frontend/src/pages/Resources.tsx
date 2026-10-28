import { useMemo, useState } from "react";

import { api, errorMessage } from "../api";
import { useAuth } from "../auth";
import { RecalcModal } from "../components/Recalc";
import { Alert, Bar, Card, ErrorBox, Field, Icon, Loading, Modal, PageHeader, Seg, Tag, useLoad } from "../components/ui";
import { d, dShort, money, moneyM, n, pct, RESOURCE_TYPE_LABEL, statusTag } from "../format";
import { useProject } from "../project";
import { href } from "../router";
import type { Allocation, RecalcResult, ResourceRow, ResourcesOverview, User } from "../types";

type Tab = "recursos" | "tareas" | "carga" | "costos";

export default function ResourcesPage({ focus }: { focus: string | null }) {
  const { projectId, version, touch } = useProject();
  const { isManager } = useAuth();
  const { data, error, loading, reload } = useLoad(() => api.get<ResourcesOverview>(`/projects/${projectId}/resources/overview`), [projectId, version]);
  const [tab, setTab] = useState<Tab>(focus ? "tareas" : "recursos");
  const [open, setOpen] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ allocation?: Allocation; task?: string } | null>(null);
  const [resourceEdit, setResourceEdit] = useState<ResourceRow | "new" | null>(null);
  const [result, setResult] = useState<{ title: string; result: RecalcResult } | null>(null);
  const [cell, setCell] = useState<{ resource: string; week: string; hours: number; capacity: number; tasks: { external_id: string; name: string; hours: number }[] } | null>(null);
  const [typeFilter, setTypeFilter] = useState("");

  const [lastFocus, setLastFocus] = useState(focus);
  if (focus !== lastFocus) {
    setLastFocus(focus);
    if (focus) setTab("tareas");
  }

  if (loading && !data) return <Loading />;
  if (error || !data) return <ErrorBox error={error ?? "Sin datos"} onRetry={() => void reload()} />;

  const humans = data.resources.filter((resource) => resource.type === "HUMANO");
  const totalHours = humans.reduce((sum, resource) => sum + (resource.total_hours ?? 0), 0);
  const resources = data.resources.filter((resource) => !typeFilter || resource.type === typeFilter);

  return (
    <>
      <PageHeader crumb="Planificación" title="Recursos y costos">
        {isManager && (
          <>
            <button className="btn" onClick={() => setResourceEdit("new")}>
              <Icon name="plus" size={14} /> Recurso
            </button>
            <button className="btn pri" onClick={() => setEditing({})}>
              <Icon name="plus" size={14} /> Asignar recurso a tarea
            </button>
          </>
        )}
      </PageHeader>
      <div className="grid g4" style={{ marginBottom: 16 }}>
        <div className="card kpi">
          <div className="l">Costo total planificado (BAC)</div>
          <div className="v">{moneyM(data.total)}</div>
          <div className="s">{money(data.total)}</div>
        </div>
        <div className="card kpi">
          <div className="l">Profesionales · horas</div>
          <div className="v">
            {humans.length} · {n(totalHours)} h
          </div>
          <div className="s">{moneyM(data.totals_by_type.HUMANO ?? 0)} en mano de obra</div>
        </div>
        <div className="card kpi">
          <div className="l">Recursos no humanos</div>
          <div className="v">{data.resources.length - humans.length}</div>
          <div className="s">{moneyM(data.total - (data.totals_by_type.HUMANO ?? 0))} en equipos, licencias y servicios</div>
        </div>
        <div className="card kpi">
          <div className="l">
            <span className={`dot ${data.overallocations.length ? "d-crit" : "d-ok"}`} /> Sobreasignaciones
          </div>
          <div className="v">{data.overallocations.length}</div>
          <div className="s">{data.overallocations.length ? `${data.overallocations.map((item) => item.resource).join(", ")}` : "Ningún profesional supera su capacidad diaria"}</div>
        </div>
      </div>
      {data.overallocations.length > 0 && (
        <div className="grid" style={{ gap: 8, marginBottom: 16 }}>
          {data.overallocations.map((item) => (
            <Alert key={`${item.resource_id}${item.from}`} level="crit">
              <b>Sobreasignación de {item.resource}:</b> {pct(item.peak_pct)} de su capacidad durante {item.days} días hábiles ({d(item.from)} → {d(item.to)}). Tareas simultáneas:{" "}
              {item.tasks.map((task) => (
                <a key={task.external_id} href={href("actividades", task.external_id)} className="dep" style={{ marginRight: 4 }}>
                  {task.external_id} · {n(task.hours_per_day, 1)} h/día
                </a>
              ))}
            </Alert>
          ))}
        </div>
      )}
      <div className="toolbar">
        <Seg
          value={tab}
          onChange={setTab}
          options={[
            { value: "recursos", label: "Por recurso" },
            { value: "tareas", label: "Por tarea" },
            { value: "carga", label: "Carga semanal" },
            { value: "costos", label: "Costos y calendario" },
          ]}
        />
        <div className="sp" />
        {tab === "recursos" && (
          <select className="search" style={{ minWidth: 180 }} value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)} aria-label="Tipo de recurso">
            <option value="">Todos los tipos</option>
            {Object.entries(RESOURCE_TYPE_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        )}
      </div>

      {tab === "recursos" && (
        <Card bodyClass="card-b scroll">
          <table className="t">
            <thead>
              <tr>
                <th>ID</th>
                <th>Recurso</th>
                <th>Tipo</th>
                <th className="num">Tarifa</th>
                <th className="num">Cap. h/día</th>
                <th className="num">Tareas</th>
                <th className="num">Horas / cantidad</th>
                <th className="num">Costo</th>
                <th>Carga máx.</th>
                <th>Usuario</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {resources.map((resource) => (
                <ResourceRows
                  key={resource.id}
                  resource={resource}
                  open={open === resource.id}
                  onToggle={() => setOpen(open === resource.id ? null : resource.id)}
                  canEdit={isManager}
                  onEdit={() => setResourceEdit(resource)}
                  onEditAllocation={(allocation) => setEditing({ allocation })}
                />
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {tab === "tareas" && (
        <Card bodyClass="card-b scroll">
          <table className="t">
            <thead>
              <tr>
                <th>Tarea</th>
                <th>Etapa</th>
                <th>Fechas</th>
                <th className="num">Días</th>
                <th>Recursos asignados (horas · h/día · costo)</th>
                <th className="num">Costo plan</th>
                <th className="num">Costo real</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {data.tasks.map((task) => (
                <tr key={task.element_id} className={focus === task.external_id ? "sel" : ""} id={`task-${task.external_id}`}>
                  <td style={{ maxWidth: 260 }}>
                    <a className="mono" href={href("actividades", task.external_id)}>
                      {task.external_id}
                    </a>{" "}
                    <span className="ell" style={{ display: "inline-block", maxWidth: 200, verticalAlign: "bottom" }} title={task.name}>
                      {task.name}
                    </span>
                  </td>
                  <td className="mono muted">{task.stage}</td>
                  <td className="mono" style={{ fontSize: 12 }}>
                    {dShort(task.start)} → {dShort(task.finish)}
                  </td>
                  <td className="num mono">{task.duration_days}</td>
                  <td>
                    <div className="alloc-list">
                      {task.assignments.map((assignment) => (
                        <button key={assignment.id} className="alloc" disabled={!isManager} onClick={() => setEditing({ allocation: assignment })} title={isManager ? "Editar asignación" : undefined}>
                          <b>{assignment.resource_external_id}</b> {assignment.resource_type === "HUMANO" ? `${n(assignment.hours)} h · ${n(assignment.hours_per_day, 1)} h/d` : `${n(assignment.quantity, 1)} ${assignment.unit ?? ""}`} · {moneyM(assignment.cost)}
                        </button>
                      ))}
                      {isManager && (
                        <button className="alloc add" onClick={() => setEditing({ task: task.external_id })} title="Asignar otro recurso">
                          +
                        </button>
                      )}
                    </div>
                  </td>
                  <td className="num mono">{money(task.planned_cost)}</td>
                  <td className="num mono">{money(task.actual_cost)}</td>
                  <td>
                    <Tag cls={statusTag(task.status)}>{Math.round(task.progress)} %</Tag>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {tab === "carga" && (
        <Card title="Carga semanal por profesional (% de su capacidad)" bodyClass="card-b scroll" actions={<span className="muted" style={{ fontSize: 12 }}>Haz clic en una celda para ver las tareas que la componen</span>}>
          <table className="heat">
            <thead>
              <tr>
                <th style={{ textAlign: "left", minWidth: 190 }}>Profesional</th>
                {data.weeks.map((week) => (
                  <th key={week} className="wk" title={`Semana del ${d(week)}`}>
                    {dShort(week)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.load.map((row) => (
                <tr key={row.resource_id}>
                  <td style={{ fontSize: 12.5, whiteSpace: "nowrap" }}>{row.name}</td>
                  {row.weeks.map((week) => (
                    <td
                      key={week.week}
                      className="h"
                      style={{ background: heat(week.pct), color: week.pct > 60 ? "#fff" : "var(--ink-2)", cursor: week.hours ? "pointer" : "default" }}
                      title={`${n(week.hours, 1)} h de ${n(week.capacity)} h (${pct(week.pct)})`}
                      onClick={() => week.hours && setCell({ resource: row.name, week: week.week, hours: week.hours, capacity: week.capacity, tasks: week.tasks })}
                    >
                      {week.hours ? Math.round(week.pct) : ""}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="legend" style={{ padding: "10px 0 0", border: 0 }}>
            {[0, 25, 50, 80, 100, 130].map((value) => (
              <span key={value}>
                <i className="lg" style={{ background: heat(value || 5) }} /> {value === 130 ? "> 100 %" : `${value} %`}
              </span>
            ))}
          </div>
        </Card>
      )}

      {tab === "costos" && (
        <div className="grid g2">
          <Card title="Costo por tipo de recurso">
            <CostBars rows={Object.entries(data.totals_by_type).map(([key, value]) => ({ label: RESOURCE_TYPE_LABEL[key] ?? key, value }))} total={data.total} />
          </Card>
          <Card title="Costo por etapa">
            <CostBars rows={data.totals_by_stage.map((row) => ({ label: `${row.external_id} · ${row.name}`, value: row.cost }))} total={data.total} />
          </Card>
          <Card title="Calendario laboral del proyecto">
            <dl className="kv">
              <dt>Jornada</dt>
              <dd>{n(data.calendar.hours_per_day)} horas por día</dd>
              <dt>Días laborales</dt>
              <dd>{data.calendar.working_days.map((day) => ["", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"][day]).join(", ")}</dd>
            </dl>
            <table className="t" style={{ marginTop: 12 }}>
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Tipo</th>
                  <th>Descripción</th>
                </tr>
              </thead>
              <tbody>
                {data.calendar.holidays.map((holiday) => (
                  <tr key={holiday.date}>
                    <td className="mono">{d(holiday.date)}</td>
                    <td>{holiday.type === "FERIADO" ? "Feriado" : holiday.type}</td>
                    <td>{holiday.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          <Card title="Cómo se calcula el costo">
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: "var(--ink-2)" }}>
              <li>Recurso humano: horas planificadas × tarifa por hora (o tarifa especial de la asignación).</li>
              <li>Recurso no humano: cantidad × costo unitario (licencias, equipos, servicios).</li>
              <li>Tarea = suma de sus asignaciones; actividad y etapa = suma de sus hijos; proyecto = suma de etapas.</li>
              <li>La carga diaria usa las horas por día de cada asignación sobre los días hábiles de la tarea; sobre 100 % se alerta.</li>
            </ul>
          </Card>
        </div>
      )}

      {cell && (
        <Modal title={`${cell.resource} · semana del ${d(cell.week)}`} onClose={() => setCell(null)}>
          <p style={{ marginTop: 0 }}>
            {n(cell.hours, 1)} h asignadas de {n(cell.capacity)} h disponibles ({pct((cell.hours / cell.capacity) * 100)}).
          </p>
          <table className="t">
            <thead>
              <tr>
                <th>Tarea</th>
                <th className="num">Horas en la semana</th>
              </tr>
            </thead>
            <tbody>
              {cell.tasks.map((task) => (
                <tr key={task.external_id}>
                  <td>
                    <a className="mono" href={href("actividades", task.external_id)}>
                      {task.external_id}
                    </a>{" "}
                    {task.name}
                  </td>
                  <td className="num mono">{n(task.hours, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Modal>
      )}
      {editing && (
        <AllocationModal
          data={data}
          allocation={editing.allocation}
          task={editing.task}
          onClose={() => setEditing(null)}
          onDone={(title, value) => {
            setEditing(null);
            setResult({ title, result: value });
            touch();
          }}
        />
      )}
      {resourceEdit && (
        <ResourceModal
          resource={resourceEdit === "new" ? undefined : resourceEdit}
          onClose={() => setResourceEdit(null)}
          onDone={() => {
            setResourceEdit(null);
            touch();
          }}
        />
      )}
      {result && <RecalcModal title={result.title} result={result.result} onClose={() => setResult(null)} />}
    </>
  );
}

function heat(value: number): string {
  if (!value) return "#f4f2ee";
  if (value > 100) return "#c23b2c";
  if (value >= 80) return "#2e7d6b";
  if (value >= 50) return "#5c9d8b";
  if (value >= 25) return "#9cc6b9";
  return "#d6ebe5";
}

function CostBars({ rows, total }: { rows: { label: string; value: number }[]; total: number }) {
  const max = Math.max(...rows.map((row) => row.value), 1);
  return (
    <div className="bars-h">
      {rows.map((row) => (
        <div className="r" key={row.label} style={{ gridTemplateColumns: "200px 1fr 90px" }}>
          <span className="ell" title={row.label}>
            {row.label}
          </span>
          <div className="tr">
            <div className="a" style={{ width: `${(row.value / max) * 100}%`, top: 2, bottom: 2 }} />
          </div>
          <span className="mono" style={{ textAlign: "right", fontSize: 12 }} title={money(row.value)}>
            {moneyM(row.value)} <span className="muted">{pct((row.value / total) * 100)}</span>
          </span>
        </div>
      ))}
    </div>
  );
}

function ResourceRows({
  resource,
  open,
  onToggle,
  canEdit,
  onEdit,
  onEditAllocation,
}: {
  resource: ResourceRow;
  open: boolean;
  onToggle: () => void;
  canEdit: boolean;
  onEdit: () => void;
  onEditAllocation: (allocation: Allocation) => void;
}) {
  const human = resource.type === "HUMANO";
  return (
    <>
      <tr onClick={onToggle} style={{ cursor: "pointer" }} className={open ? "sel" : ""}>
        <td className="mono">
          <span className="muted">{open ? "▾" : "▸"}</span> {resource.external_id}
        </td>
        <td style={{ minWidth: 210 }}>
          <b style={{ fontWeight: 500 }}>{resource.name}</b>
          {resource.role && resource.role !== resource.name && <div className="sub muted">{resource.role}</div>}
        </td>
        <td>
          <Tag cls={human ? "t-info" : "t-mute"}>{RESOURCE_TYPE_LABEL[resource.type] ?? resource.type}</Tag>
        </td>
        <td className="num mono">
          {money(resource.rate)}
          <span className="muted">/{resource.unit ?? "h"}</span>
        </td>
        <td className="num mono">{human ? n(resource.capacity_hours_per_day) : "—"}</td>
        <td className="num mono">{resource.task_count}</td>
        <td className="num mono">{human ? `${n(resource.total_hours)} h` : `${n(resource.total_quantity, 1)} ${resource.unit ?? ""}`}</td>
        <td className="num mono">{money(resource.planned_cost)}</td>
        <td style={{ minWidth: 110 }}>
          {human ? (
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <Bar value={Math.min(resource.peak_pct, 100)} cls={resource.peak_pct > 100 ? "over" : ""} />
              <span className="mono" style={{ fontSize: 11, color: resource.peak_pct > 100 ? "var(--crit)" : undefined }}>
                {Math.round(resource.peak_pct)}%
              </span>
            </div>
          ) : (
            <span className="muted">—</span>
          )}
        </td>
        <td style={{ fontSize: 12 }}>{resource.user ?? <span className="muted">—</span>}</td>
        <td>
          {canEdit && (
            <button
              className="btn sm"
              onClick={(event) => {
                event.stopPropagation();
                onEdit();
              }}
              aria-label="Editar recurso"
            >
              <Icon name="edit" size={12} />
            </button>
          )}
        </td>
      </tr>
      {open && (
        <tr className="nested">
          <td colSpan={11}>
            <table className="t">
              <thead>
                <tr>
                  <th>Tarea</th>
                  <th>Fechas</th>
                  <th className="num">{human ? "Horas" : "Cantidad"}</th>
                  {human && <th className="num">h/día</th>}
                  <th className="num">Tarifa</th>
                  <th className="num">Costo</th>
                  <th>Estado</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {resource.assignments.map((assignment) => (
                  <tr key={assignment.id}>
                    <td>
                      <a className="mono" href={href("actividades", assignment.external_id)}>
                        {assignment.external_id}
                      </a>{" "}
                      {assignment.name}
                    </td>
                    <td className="mono" style={{ fontSize: 12 }}>
                      {dShort(assignment.start)} → {dShort(assignment.finish)}
                    </td>
                    <td className="num mono">{human ? n(assignment.hours) : n(assignment.quantity, 1)}</td>
                    {human && <td className="num mono">{n(assignment.hours_per_day, 1)}</td>}
                    <td className="num mono">{money(assignment.rate)}</td>
                    <td className="num mono">{money(assignment.cost)}</td>
                    <td>
                      <Tag cls={statusTag(assignment.status)}>{Math.round(assignment.progress)} %</Tag>
                    </td>
                    <td>
                      {canEdit && (
                        <button className="btn sm" onClick={() => onEditAllocation(assignment)}>
                          Editar
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </td>
        </tr>
      )}
    </>
  );
}

function AllocationModal({
  data,
  allocation,
  task,
  onClose,
  onDone,
}: {
  data: ResourcesOverview;
  allocation?: Allocation;
  task?: string;
  onClose: () => void;
  onDone: (title: string, result: RecalcResult) => void;
}) {
  const { projectId } = useProject();
  const [element, setElement] = useState(allocation?.external_id ?? task ?? "");
  const [resourceId, setResourceId] = useState(allocation?.resource_id ?? "");
  const resource = data.resources.find((item) => item.id === resourceId);
  const human = resource ? resource.type === "HUMANO" : true;
  const [hours, setHours] = useState(String(allocation?.hours ?? ""));
  const [quantity, setQuantity] = useState(String(allocation?.quantity ?? ""));
  const [daily, setDaily] = useState(String(allocation?.hours_per_day ?? ""));
  const [rate, setRate] = useState("");
  const [effort, setEffort] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const taskRow = data.tasks.find((item) => item.external_id === element);

  const estimate = useMemo(() => {
    if (!human || !effort) return null;
    const others = (taskRow?.assignments ?? []).filter((item) => item.resource_type === "HUMANO" && item.id !== allocation?.id);
    const totalHours = others.reduce((sum, item) => sum + (item.hours ?? 0), 0) + (Number(hours) || 0);
    const totalDaily = others.reduce((sum, item) => sum + (item.hours_per_day ?? 0), 0) + (Number(daily) || Number(resource?.capacity_hours_per_day) || 0);
    return totalDaily ? Math.ceil(totalHours / totalDaily) : null;
  }, [human, effort, taskRow, allocation, hours, daily, resource]);

  async function save() {
    setBusy(true);
    setError(null);
    const payload: Record<string, unknown> = { effort_driven: effort };
    if (human) {
      payload.planned_hours = Number(hours) || 0;
      if (daily) payload.hours_per_day = Number(daily);
    } else payload.quantity = Number(quantity) || 0;
    if (rate) payload.rate_override = Number(rate);
    try {
      let value: RecalcResult;
      if (allocation) value = await api.patch<RecalcResult>(`/projects/${projectId}/allocations/${allocation.id}`, payload);
      else value = await api.post<RecalcResult>(`/projects/${projectId}/allocations`, { ...payload, element, resource_id: resourceId });
      onDone(`${element}: ${allocation ? "asignación actualizada" : `asignado ${resource?.external_id ?? "recurso"}`}`, value);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!allocation) return;
    setBusy(true);
    try {
      const value = await api.del<RecalcResult>(`/projects/${projectId}/allocations/${allocation.id}`);
      onDone(`${allocation.external_id}: se quitó ${allocation.resource_external_id}`, value);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <Modal
      title={allocation ? `Asignación ${allocation.resource_external_id} en ${allocation.external_id}` : "Asignar recurso a una tarea"}
      onClose={onClose}
      footer={
        <>
          {allocation && (
            <button className="btn danger" onClick={() => void remove()} disabled={busy}>
              Quitar asignación
            </button>
          )}
          <div style={{ flex: 1 }} />
          <button className="btn" onClick={onClose}>
            Cancelar
          </button>
          <button className="btn pri" onClick={() => void save()} disabled={busy || !element || !resourceId}>
            {busy ? "Recalculando…" : "Guardar y recalcular"}
          </button>
        </>
      }
    >
      <Field label="Tarea (subactividad)">
        <select value={element} onChange={(event) => setElement(event.target.value)} disabled={Boolean(allocation)}>
          <option value="">Selecciona…</option>
          {data.tasks.map((item) => (
            <option key={item.external_id} value={item.external_id}>
              {item.external_id} · {item.name.slice(0, 60)} ({item.duration_days} d)
            </option>
          ))}
        </select>
      </Field>
      <Field label="Recurso">
        <select value={resourceId} onChange={(event) => setResourceId(event.target.value)} disabled={Boolean(allocation)}>
          <option value="">Selecciona…</option>
          {data.resources.map((item) => (
            <option key={item.id} value={item.id}>
              {item.external_id} · {item.name} ({RESOURCE_TYPE_LABEL[item.type] ?? item.type}, {money(item.rate)}/{item.unit ?? "h"})
            </option>
          ))}
        </select>
      </Field>
      {human ? (
        <div className="row">
          <Field label="Horas planificadas">
            <input type="number" min={0} value={hours} onChange={(event) => setHours(event.target.value)} />
          </Field>
          <Field label="Horas por día" hint={resource ? `Capacidad ${n(resource.capacity_hours_per_day)} h/día` : undefined}>
            <input type="number" min={0} max={24} step={0.5} value={daily} onChange={(event) => setDaily(event.target.value)} />
          </Field>
        </div>
      ) : (
        <Field label={`Cantidad (${resource?.unit ?? "unidades"})`}>
          <input type="number" min={0} step={0.5} value={quantity} onChange={(event) => setQuantity(event.target.value)} />
        </Field>
      )}
      <Field label="Tarifa especial (opcional)" hint="Si se deja vacía se usa la tarifa del recurso.">
        <input type="number" min={0} value={rate} onChange={(event) => setRate(event.target.value)} />
      </Field>
      {human && (
        <label className="chk" style={{ marginBottom: 8 }}>
          <input type="checkbox" checked={effort} onChange={(event) => setEffort(event.target.checked)} /> Duración guiada por esfuerzo: recalcular la duración como horas totales ÷ horas diarias de todos los asignados
        </label>
      )}
      {estimate !== null && taskRow && (
        <Alert level="info">
          Duración estimada: {taskRow.duration_days} → <b>{estimate} días</b>. Si un profesional queda con más horas diarias que su capacidad, el sistema lo alertará como sobreasignación.
        </Alert>
      )}
      {error && <Alert level="crit">{error}</Alert>}
    </Modal>
  );
}

function ResourceModal({ resource, onClose, onDone }: { resource?: ResourceRow; onClose: () => void; onDone: () => void }) {
  const { projectId } = useProject();
  const { isManager } = useAuth();
  const users = useLoad(() => (isManager ? api.get<User[]>("/users") : Promise.resolve([] as User[])), []);
  const [draft, setDraft] = useState({
    external_id: resource?.external_id ?? "",
    name: resource?.name ?? "",
    resource_type: resource?.type ?? "HUMANO",
    role: resource?.role ?? "",
    rate: String(resource?.rate ?? ""),
    unit: resource?.unit ?? "hora",
    capacity_hours_per_day: String(resource?.capacity_hours_per_day ?? "8"),
    user_id: resource?.user_id ?? "",
  });
  const [error, setError] = useState<string | null>(null);
  const set = (key: keyof typeof draft) => (event: { target: { value: string } }) => setDraft((value) => ({ ...value, [key]: event.target.value }));

  async function save() {
    const payload = {
      ...draft,
      rate: Number(draft.rate) || 0,
      capacity_hours_per_day: draft.resource_type === "HUMANO" ? Number(draft.capacity_hours_per_day) || 8 : null,
      user_id: draft.user_id || null,
      role: draft.role || null,
    };
    try {
      if (resource) await api.patch(`/projects/${projectId}/resources-admin/${resource.id}`, payload);
      else await api.post(`/projects/${projectId}/resources-admin`, payload);
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <Modal
      title={resource ? `Recurso ${resource.external_id}` : "Nuevo recurso"}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            Cancelar
          </button>
          <button className="btn pri" onClick={() => void save()} disabled={!draft.external_id || !draft.name}>
            Guardar
          </button>
        </>
      }
    >
      <div className="row">
        <Field label="ID">
          <input value={draft.external_id} onChange={set("external_id")} placeholder="IN2" />
        </Field>
        <Field label="Tipo">
          <select value={draft.resource_type} onChange={set("resource_type")}>
            {Object.entries(RESOURCE_TYPE_LABEL).map(([value, label]) => (
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
      <Field label="Rol o descripción">
        <input value={draft.role} onChange={set("role")} />
      </Field>
      <div className="row">
        <Field label="Tarifa / costo unitario (CLP)">
          <input type="number" min={0} value={draft.rate} onChange={set("rate")} />
        </Field>
        <Field label="Unidad">
          <input value={draft.unit} onChange={set("unit")} />
        </Field>
        {draft.resource_type === "HUMANO" && (
          <Field label="Capacidad h/día">
            <input type="number" min={1} max={24} value={draft.capacity_hours_per_day} onChange={set("capacity_hours_per_day")} />
          </Field>
        )}
      </div>
      {draft.resource_type === "HUMANO" && (
        <Field label="Usuario vinculado" hint="El integrante vinculado puede registrar avance en las tareas de este recurso.">
          <select value={draft.user_id} onChange={set("user_id")}>
            <option value="">Sin usuario</option>
            {(users.data ?? []).map((user) => (
              <option key={user.id} value={user.id}>
                {user.full_name} · {user.email}
              </option>
            ))}
          </select>
        </Field>
      )}
      {resource && <p className="muted" style={{ fontSize: 12 }}>Cambiar la tarifa recalcula el costo de todas sus asignaciones.</p>}
      {error && <Alert level="crit">{error}</Alert>}
    </Modal>
  );
}
