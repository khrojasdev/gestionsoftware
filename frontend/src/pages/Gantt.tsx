import { useEffect, useMemo, useRef, useState } from "react";

import { api, errorMessage } from "../api";
import { useAuth } from "../auth";
import { RecalcModal } from "../components/Recalc";
import { Card, ErrorBox, Field, Icon, Loading, PageHeader, Seg, Tag, useLoad, useToast } from "../components/ui";
import { addDays, d, daysBetween, dShort, money, statusTag } from "../format";
import { useProject } from "../project";
import { href } from "../router";
import type { GanttElement, GanttFull, RecalcResult } from "../types";

const ROW = 28;
const LEFT = 400;
const MONTHS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
type Zoom = "dia" | "semana" | "mes";
const PX: Record<Zoom, number> = { dia: 20, semana: 6, mes: 2.4 };

export default function GanttPage({ focus }: { focus: string | null }) {
  const { projectId, version, touch } = useProject();
  const { data, error, loading, reload } = useLoad(() => api.get<GanttFull>(`/projects/${projectId}/gantt/full`), [projectId, version]);
  const [zoom, setZoom] = useState<Zoom>("semana");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [onlyCritical, setOnlyCritical] = useState(false);
  const [showLinks, setShowLinks] = useState(true);
  const [showBaseline, setShowBaseline] = useState(true);
  const [selected, setSelected] = useState<string | null>(focus);
  const [result, setResult] = useState<{ title: string; result: RecalcResult } | null>(null);
  const wrap = useRef<HTMLDivElement>(null);

  const px = PX[zoom];
  const model = useMemo(() => (data ? buildModel(data) : null), [data]);

  const [lastFocus, setLastFocus] = useState(focus);
  if (focus !== lastFocus) {
    setLastFocus(focus);
    if (focus) setSelected(focus);
  }

  const visible = useMemo(() => {
    if (!data || !model) return [];
    return data.elements.filter((element) => {
      let parent = element.parent;
      while (parent) {
        if (collapsed.has(parent)) return false;
        parent = model.byId.get(parent)?.parent ?? null;
      }
      if (onlyCritical && !element.is_critical) return false;
      return true;
    });
  }, [data, model, collapsed, onlyCritical]);

  useEffect(() => {
    if (!selected || !wrap.current || !model) return;
    const index = visible.findIndex((element) => element.external_id === selected);
    const element = model.byId.get(selected);
    if (index < 0 || !element) return;
    const x = element.start ? daysBetween(model.from, element.start) * px : 0;
    wrap.current.scrollTo({ top: Math.max(0, index * ROW - 160), left: Math.max(0, x - 260), behavior: "smooth" });
  }, [selected, visible, model, px]);

  if (loading && !data) return <Loading />;
  if (error || !data || !model) return <ErrorBox error={error ?? "Sin datos"} onRetry={() => void reload()} />;

  const width = (model.days + 1) * px;
  const x = (date: string | null) => (date ? daysBetween(model.from, date) * px : 0);
  const rowIndex = new Map(visible.map((element, index) => [element.external_id, index]));
  const summary = data.summary;
  const selectedElement = selected ? model.byId.get(selected) ?? null : null;

  function toggle(id: string) {
    setCollapsed((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function collapseTo(level: number) {
    setCollapsed(new Set(data!.elements.filter((element) => element.children > 0 && element.level >= level).map((element) => element.external_id)));
  }

  return (
    <>
      <PageHeader crumb="Planificación" title="Carta Gantt">
        <a className="btn" href={href("actividades")}>
          Editar actividades
        </a>
      </PageHeader>
      <div className="grid g6" style={{ marginBottom: 16 }}>
        <Stat label="Inicio" value={d(summary.start)} />
        <Stat label={`Término línea base ${data.baseline_version ?? ""}`} value={d(summary.baseline_finish)} />
        <Stat label="Término proyectado" value={d(summary.forecast_finish)} tone={summary.slip_days > 0 ? "warn" : "ok"} sub={summary.slip_days > 0 ? `+${summary.slip_days} días hábiles` : "En plazo"} />
        <Stat label="Término comprometido" value={d(summary.committed_finish)} />
        <Stat label="Reserva de plazo" value={summary.reserve_days !== null ? `${summary.reserve_days} días` : "—"} tone={(summary.reserve_days ?? 0) < 5 ? "crit" : (summary.reserve_days ?? 0) < 15 ? "warn" : "ok"} sub="hábiles hasta el compromiso" />
        <Stat label="Tareas en ruta crítica" value={String(summary.critical_count)} />
      </div>
      <Card bodyClass="" className="gantt-card">
        <div className="toolbar" style={{ padding: "12px 16px 0" }}>
          <Seg
            value={zoom}
            onChange={setZoom}
            options={[
              { value: "dia", label: "Días" },
              { value: "semana", label: "Semanas" },
              { value: "mes", label: "Meses" },
            ]}
          />
          <button className="btn sm" onClick={() => collapseTo(0)}>
            Solo etapas
          </button>
          <button className="btn sm" onClick={() => collapseTo(1)}>
            Hasta actividades
          </button>
          <button className="btn sm" onClick={() => setCollapsed(new Set())}>
            Expandir todo
          </button>
          <div className="sp" />
          <label className="chk">
            <input type="checkbox" checked={onlyCritical} onChange={(event) => setOnlyCritical(event.target.checked)} /> Solo ruta crítica
          </label>
          <label className="chk">
            <input type="checkbox" checked={showLinks} onChange={(event) => setShowLinks(event.target.checked)} /> Precedencias
          </label>
          <label className="chk">
            <input type="checkbox" checked={showBaseline} onChange={(event) => setShowBaseline(event.target.checked)} /> Línea base
          </label>
          <button
            className="btn sm"
            onClick={() => {
              if (!wrap.current || !data.cutoff) return;
              wrap.current.scrollTo({ left: Math.max(0, x(data.cutoff) - 300), behavior: "smooth" });
            }}
          >
            Ir a fecha de corte
          </button>
        </div>
        <div className="gwrap" ref={wrap} style={{ maxHeight: "calc(100vh - 290px)", marginTop: 12 }}>
          <div className="ghead" style={{ width: LEFT + width }}>
            <div className="gl" style={{ height: 40 }}>
              <span className="c1">ID</span>
              <span className="c2">Nombre</span>
              <span className="c3">Días</span>
              <span className="c4">Av.</span>
            </div>
            <div className="gr" style={{ width, height: 40 }}>
              {model.months.map((month) => (
                <div key={month.date} className="gm" style={{ left: x(month.date), width: month.days * px }}>
                  {px * month.days > 34 ? `${MONTHS[month.month]} ${String(month.year).slice(2)}` : ""}
                </div>
              ))}
              {data.cutoff && (
                <span className="gcut" style={{ left: x(data.cutoff) }}>
                  Corte {dShort(data.cutoff)}
                </span>
              )}
              {summary.committed_finish && (
                <span className="gcomm" style={{ left: x(summary.committed_finish) + px }}>
                  Compromiso {dShort(summary.committed_finish)}
                </span>
              )}
              {zoom !== "mes" &&
                model.weeks.map((week) => (
                  <div key={week} className="gw" style={{ left: x(week) }}>
                    {zoom === "dia" ? dShort(week) : week.slice(8, 10)}
                  </div>
                ))}
            </div>
          </div>
          <div className="gbody" style={{ position: "relative", width: LEFT + width }}>
            <div className="gbg" style={{ left: LEFT, width, height: visible.length * ROW }}>
              {zoom !== "mes" && model.weeks.map((week) => <div key={week} className="gweek" style={{ left: x(week) }} />)}
              {data.holidays.map((holiday) => (
                <div key={holiday} className="ghol" style={{ left: x(holiday), width: Math.max(px, 2) }} title={`Feriado ${d(holiday)}`} />
              ))}
              {model.weekends && zoom === "dia" && model.weekends.map((day) => <div key={day} className="gwe" style={{ left: x(day), width: px }} />)}
              {data.cutoff && (
                <div className="gtoday" style={{ left: x(data.cutoff) }} />
              )}
              {summary.committed_finish && (
                <div className="gcommit" style={{ left: x(summary.committed_finish) + px }} />
              )}
            </div>
            {visible.map((element) => (
              <Row
                key={element.id}
                element={element}
                x={x}
                px={px}
                width={width}
                collapsed={collapsed.has(element.external_id)}
                onToggle={() => toggle(element.external_id)}
                selected={selected === element.external_id}
                onSelect={() => setSelected(element.external_id)}
                showBaseline={showBaseline}
              />
            ))}
            {showLinks && (
              <svg className="glinks" style={{ left: LEFT }} width={width} height={visible.length * ROW} aria-hidden="true">
                <defs>
                  <marker id="arr" viewBox="0 0 6 6" refX="5" refY="3" markerWidth="6" markerHeight="6" orient="auto">
                    <path d="M0 0L6 3L0 6z" fill="#8a9198" />
                  </marker>
                  <marker id="arr-c" viewBox="0 0 6 6" refX="5" refY="3" markerWidth="6" markerHeight="6" orient="auto">
                    <path d="M0 0L6 3L0 6z" fill="#c23b2c" />
                  </marker>
                </defs>
                {data.links.map((link) => {
                  const fromIndex = rowIndex.get(link.from);
                  const toIndex = rowIndex.get(link.to);
                  const from = model.byId.get(link.from);
                  const to = model.byId.get(link.to);
                  if (fromIndex === undefined || toIndex === undefined || !from || !to) return null;
                  const fromEnd = link.type === "FS" || link.type === "FF";
                  const toEnd = link.type === "FF" || link.type === "SF";
                  const fx = fromEnd ? x(from.finish) + (from.kind === "HITO" ? px / 2 + 6 : px) : x(from.start) - (from.kind === "HITO" ? -px / 2 + 6 : 0);
                  const tx = toEnd ? x(to.finish) + (to.kind === "HITO" ? px / 2 + 6 : px) : x(to.start) + (to.kind === "HITO" ? px / 2 - 6 : 0);
                  const fy = fromIndex * ROW + ROW / 2;
                  const ty = toIndex * ROW + ROW / 2;
                  const d1 = fromEnd ? 6 : -6;
                  const d2 = toEnd ? 6 : -6;
                  const midY = toIndex > fromIndex ? ty - ROW / 2 : ty + ROW / 2;
                  const path = `M${fx} ${fy} H${fx + d1} V${midY} H${tx + d2} V${ty} H${tx}`;
                  const highlight = selected && (link.from === selected || link.to === selected);
                  return (
                    <path
                      key={link.id}
                      d={path}
                      fill="none"
                      stroke={link.critical ? "#c23b2c" : "#9aa1a8"}
                      strokeWidth={highlight ? 2 : 1}
                      opacity={selected ? (highlight ? 0.95 : 0.18) : link.critical ? 0.6 : 0.5}
                      markerEnd={`url(#${link.critical ? "arr-c" : "arr"})`}
                    />
                  );
                })}
              </svg>
            )}
          </div>
        </div>
        <div className="legend">
          <span>
            <i className="lg" style={{ background: "var(--real)" }} /> Avance real
          </span>
          <span>
            <i className="lg" style={{ background: "var(--real-soft)", border: "1px solid #9fcabe" }} /> Plan vigente
          </span>
          <span>
            <i className="lg" style={{ background: "#f7dcd7", border: "1px solid var(--crit)" }} /> Ruta crítica
          </span>
          <span>
            <i className="lg" style={{ background: "#fbe7c1", border: "1px solid var(--warn)" }} /> Atrasada
          </span>
          <span>
            <i className="lg" style={{ background: "repeating-linear-gradient(-45deg,#e9f3f0 0 4px,#c9ded8 4px 8px)" }} /> Desplazamiento proyectado
          </span>
          <span>
            <i className="lg" style={{ background: "var(--plan)", height: 4 }} /> Línea base
          </span>
          <span>
            <i className="lg" style={{ background: "var(--accent)", width: 3 }} /> Fecha de corte
          </span>
          <span>FS · SS · FF · SF = tipos de precedencia</span>
        </div>
      </Card>
      {selectedElement && <Panel key={`${selectedElement.id}-${selectedElement.duration_days}`} element={selectedElement} data={data} onClose={() => setSelected(null)} onDone={(title, value) => { setResult({ title, result: value }); touch(); }} />}
      {result && <RecalcModal title={result.title} result={result.result} onClose={() => setResult(null)} />}
    </>
  );
}

function Stat({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: "ok" | "warn" | "crit" }) {
  return (
    <div className="card kpi">
      <div className="l">
        {tone && <span className={`dot d-${tone}`} />}
        {label}
      </div>
      <div className="v" style={{ fontSize: 19 }}>
        {value}
      </div>
      {sub && <div className="s">{sub}</div>}
    </div>
  );
}

function Row({
  element,
  x,
  px,
  width,
  collapsed,
  onToggle,
  selected,
  onSelect,
  showBaseline,
}: {
  element: GanttElement;
  x: (date: string | null) => number;
  px: number;
  width: number;
  collapsed: boolean;
  onToggle: () => void;
  selected: boolean;
  onSelect: () => void;
  showBaseline: boolean;
}) {
  const level = element.kind === "ETAPA" ? 1 : element.kind === "ACTIVIDAD" ? 2 : 3;
  const start = element.start;
  const finish = element.finish;
  const late = element.status === "ATRASADA";
  const barClass = `gb ${element.is_critical ? "crit" : ""} ${late ? "late" : ""} ${element.progress >= 100 ? "done" : ""}`;
  const title = `${element.external_id} · ${element.name}\nPlan ${d(start)} → ${d(finish)}\nLínea base ${d(element.baseline_start)} → ${d(element.baseline_finish)}\nProyección ${d(element.forecast_start)} → ${d(element.forecast_finish)}\nAvance ${Math.round(element.progress)} % (plan ${Math.round(element.planned_pct)} %)`;
  return (
    <div className={`grow lv${level} ${selected ? "gsel" : ""}`} onClick={onSelect}>
      <div className="gl">
        <span className="c1">{element.external_id}</span>
        <span className="c2" title={element.name}>
          {element.children > 0 ? (
            <button
              className="tg"
              onClick={(event) => {
                event.stopPropagation();
                onToggle();
              }}
              aria-label={collapsed ? "Expandir" : "Contraer"}
            >
              {collapsed ? "▸" : "▾"}
            </button>
          ) : (
            <span className="tg" />
          )}
          {element.kind === "HITO" && <span className="diamond" />}
          {element.name}
        </span>
        <span className="c3">{element.kind === "HITO" ? "◆" : element.duration_days ?? ""}</span>
        <span className="c4" style={{ color: late ? "var(--warn)" : undefined }}>
          {Math.round(element.progress)}%
        </span>
      </div>
      <div className="gr" style={{ width, height: ROW }} title={title}>
        {start && finish && element.kind === "HITO" && (
          <>
            {showBaseline && element.baseline_finish && element.baseline_finish !== finish && <div className="gms ghost" style={{ left: x(element.baseline_finish) + px / 2 - 6 }} />}
            <div className={`gms ${element.progress >= 100 ? "done" : element.slip_days > 0 || element.status === "EN_RIESGO" ? "risk" : ""}`} style={{ left: x(finish) + px / 2 - 6 }} />
            {element.forecast_finish && element.forecast_finish !== finish && element.progress < 100 && <div className="gms fut" style={{ left: x(element.forecast_finish) + px / 2 - 6 }} />}
            <span className="glabel" style={{ left: x(element.forecast_finish ?? finish) + px / 2 + 10 }}>
              {dShort(element.forecast_finish ?? finish)}
            </span>
          </>
        )}
        {start && finish && element.kind !== "HITO" && element.kind !== "SUBACTIVIDAD" && (
          <>
            <div className={`gsum ${element.kind === "ACTIVIDAD" ? "pk" : ""}`} style={{ left: x(start), width: Math.max((daysBetween(start, finish) + 1) * px, 2) }} />
            {element.forecast_finish && element.forecast_finish > finish && (
              <div className="gsum-ext" style={{ left: x(finish) + px, width: daysBetween(finish, element.forecast_finish) * px }} />
            )}
          </>
        )}
        {start && finish && element.kind === "SUBACTIVIDAD" && (
          <>
            <div className={barClass} style={{ left: x(start), width: Math.max((daysBetween(start, finish) + 1) * px, 3) }}>
              <i style={{ width: `${Math.min(100, element.progress)}%` }} />
            </div>
            {element.forecast_finish && element.forecast_finish > finish && (
              <div className={`gb fut ${element.is_critical ? "crit" : ""}`} style={{ left: x(addDays(finish, 1)), width: daysBetween(finish, element.forecast_finish) * px }} />
            )}
            {showBaseline && element.baseline_start && element.baseline_finish && (
              <div className="gbase" style={{ left: x(element.baseline_start), width: Math.max((daysBetween(element.baseline_start, element.baseline_finish) + 1) * px, 2) }} />
            )}
            {px >= 6 && element.resources.length > 0 && (
              <span className="glabel" style={{ left: x(element.forecast_finish && element.forecast_finish > finish ? element.forecast_finish : finish) + px + 6 }}>
                {element.resources[0].split(" ")[0]}
                {element.resources.length > 1 ? ` +${element.resources.length - 1}` : ""}
              </span>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function Panel({ element, data, onClose, onDone }: { element: GanttElement; data: GanttFull; onClose: () => void; onDone: (title: string, result: RecalcResult) => void }) {
  const { isManager } = useAuth();
  const { projectId } = useProject();
  const toast = useToast();
  const [duration, setDuration] = useState(String(element.duration_days ?? ""));
  const [busy, setBusy] = useState(false);
  const successors = data.links.filter((link) => link.from === element.external_id);

  async function save() {
    setBusy(true);
    try {
      const result = await api.patch<RecalcResult>(`/projects/${projectId}/elements/${element.external_id}`, { duration_days: Number(duration) });
      onDone(`${element.external_id}: duración ${element.duration_days} → ${duration} días`, result);
    } catch (err) {
      toast("crit", errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className="gpanel card">
      <div className="card-h">
        <h3>
          <span className="mono muted">{element.external_id}</span> {element.name}
        </h3>
        <div className="sp" />
        <button className="btn sm" onClick={onClose} aria-label="Cerrar panel">
          <Icon name="x" size={13} />
        </button>
      </div>
      <div className="card-b">
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
          <Tag cls={statusTag(element.status)}>{element.status_label}</Tag>
          {element.is_critical && <Tag cls="t-crit">Ruta crítica</Tag>}
          {element.slip_days > 0 && <Tag cls="t-warn">Desplazada {element.slip_days} d</Tag>}
        </div>
        <dl className="kv" style={{ gridTemplateColumns: "110px 1fr", fontSize: 12.5 }}>
          <dt>Plan vigente</dt>
          <dd className="mono">
            {d(element.start)} → {d(element.finish)}
          </dd>
          <dt>Línea base</dt>
          <dd className="mono">
            {d(element.baseline_start)} → {d(element.baseline_finish)}
          </dd>
          <dt>Proyección</dt>
          <dd className="mono">{d(element.forecast_finish)}</dd>
          <dt>Avance</dt>
          <dd>
            {Math.round(element.progress)} % (plan {Math.round(element.planned_pct)} %)
          </dd>
          <dt>Holgura total</dt>
          <dd>{element.total_slack ?? "—"} días</dd>
          <dt>Costo plan</dt>
          <dd className="mono">{money(element.planned_cost)}</dd>
          <dt>Predecesoras</dt>
          <dd>
            {element.predecessors.length
              ? element.predecessors.map((dep) => (
                  <span key={dep.id} className="dep" style={{ marginRight: 3 }}>
                    {dep.predecessor} {dep.type}
                    {dep.lag_days ? `${dep.lag_days > 0 ? "+" : ""}${dep.lag_days}` : ""}
                  </span>
                ))
              : "—"}
          </dd>
          <dt>Sucesoras</dt>
          <dd>
            {successors.length
              ? successors.map((link) => (
                  <span key={link.id} className="dep" style={{ marginRight: 3 }}>
                    {link.to} {link.type}
                  </span>
                ))
              : "—"}
          </dd>
          {element.resources.length > 0 && (
            <>
              <dt>Recursos</dt>
              <dd>{element.resources.join(", ")}</dd>
            </>
          )}
        </dl>
        {isManager && element.kind === "SUBACTIVIDAD" && (
          <div className="row" style={{ alignItems: "flex-end", marginTop: 12 }}>
            <Field label="Duración (días hábiles)">
              <input type="number" min={1} value={duration} onChange={(event) => setDuration(event.target.value)} />
            </Field>
            <button className="btn pri" style={{ flex: "none", marginBottom: 12 }} disabled={busy || Number(duration) === element.duration_days || Number(duration) < 1} onClick={() => void save()}>
              {busy ? "Recalculando…" : "Recalcular"}
            </button>
          </div>
        )}
        <div style={{ display: "flex", gap: 8 }}>
          <a className="btn sm" href={href("actividades", element.external_id)}>
            Abrir en Actividades
          </a>
          {element.kind === "HITO" && (
            <a className="btn sm" href={href("hitos", element.external_id)}>
              Criterios del hito
            </a>
          )}
        </div>
      </div>
    </aside>
  );
}

type Model = {
  from: string;
  days: number;
  byId: Map<string, GanttElement>;
  months: { date: string; month: number; year: number; days: number }[];
  weeks: string[];
  weekends: string[];
};

function buildModel(data: GanttFull): Model {
  const dates: string[] = [];
  data.elements.forEach((element) => {
    [element.start, element.finish, element.baseline_start, element.baseline_finish, element.forecast_finish].forEach((value) => value && dates.push(value));
  });
  if (data.summary.committed_finish) dates.push(data.summary.committed_finish);
  if (data.cutoff) dates.push(data.cutoff);
  dates.sort();
  const first = dates[0] ?? new Date().toISOString().slice(0, 10);
  const last = dates[dates.length - 1] ?? first;
  // start on the Monday before the first date
  const firstDate = new Date(`${first}T00:00:00Z`);
  const shift = (firstDate.getUTCDay() + 6) % 7;
  const from = addDays(first, -shift - 7);
  const to = addDays(last, 21);
  const days = daysBetween(from, to);
  const months: Model["months"] = [];
  const weeks: string[] = [];
  const weekends: string[] = [];
  for (let i = 0; i <= days; i += 1) {
    const date = addDays(from, i);
    const value = new Date(`${date}T00:00:00Z`);
    if (value.getUTCDate() === 1 || i === 0) {
      const monthEnd = new Date(Date.UTC(value.getUTCFullYear(), value.getUTCMonth() + 1, 0));
      const end = monthEnd.toISOString().slice(0, 10) > to ? to : monthEnd.toISOString().slice(0, 10);
      months.push({ date, month: value.getUTCMonth(), year: value.getUTCFullYear(), days: daysBetween(date, end) + 1 });
    }
    if (value.getUTCDay() === 1) weeks.push(date);
    if (value.getUTCDay() === 0 || value.getUTCDay() === 6) weekends.push(date);
  }
  return { from, days, byId: new Map(data.elements.map((element) => [element.external_id, element])), months, weeks, weekends };
}
