import { useRef, useState } from "react";

import { api, errorMessage } from "../api";
import { useAuth } from "../auth";
import { Sparkline } from "../components/charts";
import { Alert, Card, ErrorBox, Field, Icon, Loading, Modal, PageHeader, Seg, Tag, useLoad, useToast } from "../components/ui";
import { dt, KPI_LABEL, kpiDot, kpiTag, kpiValue, n } from "../format";
import { useProject } from "../project";
import type { Kpi, KpiBoard } from "../types";

type Category = "PROYECTO" | "CAMBIO";

function renderValue(value: unknown): string {
  if (typeof value === "number") return Math.abs(value) >= 1000 ? n(value) : n(value, Number.isInteger(value) ? 0 : 2);
  if (Array.isArray(value)) return `${value.length} elementos`;
  if (value === null || value === undefined) return "—";
  return String(value);
}

export default function KpiPage({ focus }: { focus: string | null }) {
  const { projectId, version, touch } = useProject();
  const { isManager } = useAuth();
  const toast = useToast();
  const { data, error, loading, reload } = useLoad(() => api.get<KpiBoard>(`/projects/${projectId}/kpis/board`), [projectId, version]);
  const [category, setCategory] = useState<Category>("PROYECTO");
  const [selected, setSelected] = useState<string | null>(focus);
  const [creating, setCreating] = useState(false);

  const [synced, setSynced] = useState<string | null>(null);
  if (data && focus && synced !== focus) {
    setSynced(focus);
    const found = data.kpis.find((kpi) => kpi.code === focus);
    if (found) {
      setCategory(found.category);
      setSelected(found.code);
    }
  }

  if (loading && !data) return <Loading />;
  if (error || !data) return <ErrorBox error={error ?? "Sin datos"} onRetry={() => void reload()} />;
  const kpis = data.kpis.filter((kpi) => kpi.category === category);
  const current = kpis.find((kpi) => kpi.code === selected) ?? kpis[0] ?? null;
  const counts = (["VERDE", "AMARILLO", "ROJO"] as const).map((status) => kpis.filter((kpi) => kpi.status === status).length);

  return (
    <>
      <PageHeader crumb="Control" title="Administrador de KPI">
        {isManager && (
          <>
            <button
              className="btn"
              onClick={async () => {
                try {
                  await api.post(`/projects/${projectId}/kpis/snapshot`);
                  toast("ok", "KPI recalculados y registrados en el historial a la fecha de corte.");
                  touch();
                } catch (err) {
                  toast("crit", errorMessage(err));
                }
              }}
            >
              <Icon name="refresh" size={14} /> Recalcular
            </button>
            <button className="btn pri" onClick={() => setCreating(true)}>
              <Icon name="plus" size={14} /> Nuevo KPI
            </button>
          </>
        )}
      </PageHeader>
      <div className="toolbar">
        <Seg
          value={category}
          onChange={(value) => {
            setCategory(value);
            setSelected(data.kpis.find((kpi) => kpi.category === value)?.code ?? null);
          }}
          options={[
            { value: "PROYECTO", label: "Proyecto e hitos" },
            { value: "CAMBIO", label: "Gestión del cambio" },
          ]}
        />
        <span className="muted" style={{ fontSize: 12.5 }}>
          <span className="dot d-ok" /> {counts[0]} verdes · <span className="dot d-warn" /> {counts[1]} amarillos · <span className="dot d-crit" /> {counts[2]} rojos
        </span>
        <div className="sp" />
        <span className="muted" style={{ fontSize: 12 }}>
          Calculados a la fecha de corte; se recalculan con cada cambio de avance, duración, recursos o solicitudes.
        </span>
      </div>
      <div className="split" style={{ gridTemplateColumns: "minmax(0,1fr) 440px" }}>
        <Card bodyClass="card-b scroll">
          <table className="t">
            <thead>
              <tr>
                <th>Código</th>
                <th>Indicador</th>
                <th className="num">Valor</th>
                <th>Estado</th>
                <th>Umbral verde</th>
                <th>Umbral amarillo</th>
              </tr>
            </thead>
            <tbody>
              {kpis.map((kpi) => (
                <tr key={kpi.id} className={current?.id === kpi.id ? "sel" : ""} onClick={() => setSelected(kpi.code)} style={{ cursor: "pointer" }}>
                  <td className="mono">{kpi.code}</td>
                  <td>
                    {kpi.name} {kpi.is_additional && <Tag cls="t-acc">Adicional</Tag>}
                    <div className="sub mono muted">{kpi.formula}</div>
                  </td>
                  <td className="num mono" style={{ fontWeight: 600 }}>
                    {kpiValue(kpi.value, kpi.unit)}
                  </td>
                  <td>
                    <Tag cls={kpiTag(kpi.status)}>{KPI_LABEL[kpi.status]}</Tag>
                  </td>
                  <td className="mono" style={{ fontSize: 12 }}>
                    {kpi.green_threshold !== null ? `${kpi.direction === "MENOR" ? "≤" : "≥"} ${kpiValue(kpi.green_threshold, kpi.unit)}` : "—"}
                  </td>
                  <td className="mono" style={{ fontSize: 12 }}>
                    {kpi.yellow_threshold !== null ? `${kpi.direction === "MENOR" ? "≤" : "≥"} ${kpiValue(kpi.yellow_threshold, kpi.unit)}` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <div className="drawer">{current && <KpiDetail key={current.id + version} kpi={current} board={data} canEdit={isManager} onSaved={touch} />}</div>
      </div>
      <div className="grid g2" style={{ marginTop: 16 }}>
        <Card title="Variables disponibles para fórmulas" bodyClass="card-b scroll" className="vars-card">
          <table className="t">
            <thead>
              <tr>
                <th>Variable</th>
                <th>Descripción</th>
                <th className="num">Valor actual</th>
                <th>Origen</th>
              </tr>
            </thead>
            <tbody>
              {data.variables.map((variable) => (
                <tr key={variable.code}>
                  <td className="mono">{variable.code}</td>
                  <td style={{ fontSize: 12.5 }}>
                    {variable.description}
                    <div className="sub muted">{variable.calculation}</div>
                  </td>
                  <td className="num mono">{renderValue(variable.value)}</td>
                  <td style={{ fontSize: 12 }} className="muted">
                    {variable.source}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
        <Card title="Mediciones manuales (gestión del cambio)">
          <p className="muted" style={{ marginTop: 0, fontSize: 12.5 }}>
            Indicadores que no provienen del sistema (encuestas de adopción y registro de capacitaciones). Al guardarlos se recalculan C11 y C12.
          </p>
          {data.manual.map((metric) => (
            <ManualRow key={metric.code} metric={metric} canEdit={isManager} onSaved={touch} />
          ))}
          <h4 className="h4" style={{ marginTop: 16 }}>
            Operadores permitidos
          </h4>
          <p className="mono" style={{ fontSize: 12 }}>
            + - * / ( ) · comparaciones (&gt; &lt; &gt;= &lt;= == !=) · sum(…) · avg(…) · min(…) · max(…) · count(LISTA) · if(condición, sí, no)
          </p>
        </Card>
      </div>
      {creating && <KpiCreateModal category={category} board={data} onClose={() => setCreating(false)} onSaved={(code) => { setCreating(false); setSelected(code); touch(); }} />}
    </>
  );
}

function KpiDetail({ kpi, board, canEdit, onSaved }: { kpi: Kpi; board: KpiBoard; canEdit: boolean; onSaved: () => void }) {
  const { projectId } = useProject();
  const toast = useToast();
  const [formula, setFormula] = useState(kpi.formula);
  const [green, setGreen] = useState(kpi.green_threshold?.toString() ?? "");
  const [yellow, setYellow] = useState(kpi.yellow_threshold?.toString() ?? "");
  const [target, setTarget] = useState(kpi.target?.toString() ?? "");
  const [test, setTest] = useState<{ value: number; substituted: string | null } | null>(null);
  const [testError, setTestError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const area = useRef<HTMLTextAreaElement>(null);
  const dirty = formula !== kpi.formula || green !== (kpi.green_threshold?.toString() ?? "") || yellow !== (kpi.yellow_threshold?.toString() ?? "") || target !== (kpi.target?.toString() ?? "");
  const breakdown = kpi.breakdown;
  const higher = Number(green) >= Number(yellow);

  async function runTest() {
    setTestError(null);
    setTest(null);
    try {
      const result = await api.post<{ value: number; breakdown: { substituted: string | null } }>(`/projects/${projectId}/kpis/test`, { formula });
      setTest({ value: result.value, substituted: result.breakdown.substituted });
    } catch (err) {
      setTestError(errorMessage(err));
    }
  }

  async function save() {
    setBusy(true);
    try {
      const payload: Record<string, unknown> = {
        green_threshold: green === "" ? null : Number(green),
        yellow_threshold: yellow === "" ? null : Number(yellow),
        target: target === "" ? null : Number(target),
      };
      if (formula !== kpi.formula) payload.formula = formula;
      await api.put(`/projects/${projectId}/kpi-config/${kpi.id}`, payload);
      toast("ok", `${kpi.code} actualizado${formula !== kpi.formula ? " (nueva versión de fórmula)" : ""}.`);
      onSaved();
    } catch (err) {
      toast("crit", errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function insert(code: string) {
    const element = area.current;
    if (!element) return setFormula((value) => `${value} ${code}`);
    const start = element.selectionStart ?? formula.length;
    const end = element.selectionEnd ?? formula.length;
    const next = `${formula.slice(0, start)}${code}${formula.slice(end)}`;
    setFormula(next);
    requestAnimationFrame(() => {
      element.focus();
      element.selectionStart = element.selectionEnd = start + code.length;
    });
  }

  return (
    <div className="grid">
      <Card
        title={
          <>
            <span className="mono muted">{kpi.code}</span> {kpi.name}
          </>
        }
        actions={<Tag cls={kpiTag(kpi.status)}>{KPI_LABEL[kpi.status]}</Tag>}
      >
        <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
          <span className={`dot ${kpiDot(kpi.status)}`} />
          <span style={{ fontSize: 30, fontWeight: 600, letterSpacing: "-.5px" }}>{kpiValue(kpi.value, kpi.unit)}</span>
          {kpi.target !== null && <span className="muted">meta {kpiValue(kpi.target, kpi.unit)}</span>}
        </div>
        {kpi.description && <p className="muted" style={{ fontSize: 12.5, margin: "6px 0 10px" }}>{kpi.description}</p>}
        <div className="code">
          <span className="o">{kpi.code}</span> = <span className="v">{breakdown.formula}</span>
          {breakdown.substituted && (
            <>
              <br />
              <span className="o">{kpi.code}</span> = {breakdown.substituted}
              <br />
              <span className="o">{kpi.code}</span> = <span className="v">{kpi.value !== null ? n(kpi.value, 4) : "—"}</span>
            </>
          )}
          {breakdown.error && (
            <>
              <br />
              <span style={{ color: "#f3a59a" }}>{breakdown.error}</span>
            </>
          )}
        </div>
        {(breakdown.variables_detail ?? []).length > 0 && (
          <table className="t" style={{ marginTop: 10 }}>
            <thead>
              <tr>
                <th>Variable</th>
                <th className="num">Valor</th>
                <th>Cómo se obtiene</th>
              </tr>
            </thead>
            <tbody>
              {(breakdown.variables_detail ?? []).map((variable) => (
                <tr key={variable.code}>
                  <td className="mono">{variable.code}</td>
                  <td className="num mono">{renderValue(variable.value)}</td>
                  <td style={{ fontSize: 12 }}>
                    {variable.description}
                    <div className="sub muted">
                      {variable.calculation} · {variable.source}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <h4 className="h4" style={{ marginTop: 14 }}>
          Tendencia ({kpi.history.length} mediciones)
        </h4>
        <Sparkline points={kpi.history} green={kpi.green_threshold} yellow={kpi.yellow_threshold} />
      </Card>

      <Card title={canEdit ? "Configurar fórmula y umbrales" : "Fórmula y umbrales"}>
        <Field label="Fórmula">
          <textarea ref={area} className="mono" value={formula} onChange={(event) => setFormula(event.target.value)} disabled={!canEdit} rows={2} spellCheck={false} />
        </Field>
        {canEdit && (
          <div className="var-chips">
            {board.variables.slice(0, 40).map((variable) => (
              <button key={variable.code} className="chip" title={variable.description} onClick={() => insert(variable.code)}>
                {variable.code}
              </button>
            ))}
          </div>
        )}
        <div className="thr" style={{ margin: "10px 0" }}>
          <div style={{ background: "var(--ok-soft)" }}>
            <label className="muted" style={{ fontSize: 11 }}>
              Verde {higher ? "≥" : "≤"}
            </label>
            <input value={green} onChange={(event) => setGreen(event.target.value)} disabled={!canEdit} type="number" step="any" />
          </div>
          <div style={{ background: "var(--warn-soft)" }}>
            <label className="muted" style={{ fontSize: 11 }}>
              Amarillo {higher ? "≥" : "≤"}
            </label>
            <input value={yellow} onChange={(event) => setYellow(event.target.value)} disabled={!canEdit} type="number" step="any" />
          </div>
          <div style={{ background: "var(--crit-soft)" }}>
            <label className="muted" style={{ fontSize: 11 }}>
              Rojo
            </label>
            <div className="mono" style={{ fontSize: 12, paddingTop: 6 }}>
              {yellow === "" ? "—" : `${higher ? "<" : ">"} ${yellow}`}
            </div>
          </div>
        </div>
        <Field label="Meta">
          <input value={target} onChange={(event) => setTarget(event.target.value)} disabled={!canEdit} type="number" step="any" />
        </Field>
        <p className="muted" style={{ fontSize: 12, marginTop: 0 }}>
          Si el umbral verde es mayor que el amarillo, un valor más alto es mejor; si es menor, un valor más bajo es mejor. Sin umbrales el KPI es informativo.
        </p>
        {canEdit && (
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="btn" onClick={() => void runTest()}>
              <Icon name="play" size={12} /> Probar fórmula
            </button>
            <button className="btn pri" disabled={!dirty || busy} onClick={() => void save()}>
              Guardar
            </button>
            {dirty && (
              <button
                className="btn"
                onClick={() => {
                  setFormula(kpi.formula);
                  setGreen(kpi.green_threshold?.toString() ?? "");
                  setYellow(kpi.yellow_threshold?.toString() ?? "");
                  setTarget(kpi.target?.toString() ?? "");
                  setTest(null);
                }}
              >
                Descartar
              </button>
            )}
          </div>
        )}
        {test && (
          <div style={{ marginTop: 10 }}>
            <Alert level="ok">
              Resultado: <b className="mono">{n(test.value, 4)}</b>
              {test.substituted && <span className="mono"> = {test.substituted}</span>}
            </Alert>
          </div>
        )}
        {testError && (
          <div style={{ marginTop: 10 }}>
            <Alert level="crit">{testError}</Alert>
          </div>
        )}
      </Card>

      {kpi.versions.length > 0 && (
        <Card title={`Versiones de la fórmula (${kpi.versions.length})`}>
          {kpi.versions
            .slice()
            .reverse()
            .map((item) => (
              <div className="ev" key={item.version}>
                <span className="when">v{item.version}</span>
                <div>
                  <span className="mono">{item.formula}</span>
                  <div className="sub muted">
                    {item.changed_by ?? "Sistema"} · {dt(item.changed_at)}
                    {item.previous && (
                      <>
                        {" "}
                        · antes <span className="mono">{item.previous}</span>
                      </>
                    )}
                  </div>
                </div>
              </div>
            ))}
        </Card>
      )}
    </div>
  );
}

function ManualRow({ metric, canEdit, onSaved }: { metric: KpiBoard["manual"][number]; canEdit: boolean; onSaved: () => void }) {
  const { projectId } = useProject();
  const toast = useToast();
  const [value, setValue] = useState(metric.value?.toString() ?? "");
  return (
    <div className="row" style={{ alignItems: "flex-end" }}>
      <Field label={metric.label} hint={metric.updated_at ? `Actualizado ${dt(metric.updated_at)}` : undefined}>
        <input type="number" min={0} max={100} step="any" value={value} onChange={(event) => setValue(event.target.value)} disabled={!canEdit} />
      </Field>
      {canEdit && (
        <button
          className="btn"
          style={{ flex: "none", marginBottom: 30 }}
          disabled={value === (metric.value?.toString() ?? "")}
          onClick={async () => {
            try {
              await api.put(`/projects/${projectId}/manual-metrics`, { code: metric.code, value: Number(value) });
              toast("ok", "Medición guardada y KPI recalculados.");
              onSaved();
            } catch (err) {
              toast("crit", errorMessage(err));
            }
          }}
        >
          Guardar
        </button>
      )}
    </div>
  );
}

function KpiCreateModal({ category, board, onClose, onSaved }: { category: Category; board: KpiBoard; onClose: () => void; onSaved: (code: string) => void }) {
  const { projectId } = useProject();
  const [draft, setDraft] = useState({ code: "", name: "", description: "", formula: "", unit: "", green: "", yellow: "", category, additional: true });
  const [error, setError] = useState<string | null>(null);
  const set = (key: keyof typeof draft) => (event: { target: { value: string } }) => setDraft((value) => ({ ...value, [key]: event.target.value }));
  async function save() {
    try {
      await api.post(`/projects/${projectId}/kpi-config`, {
        code: draft.code,
        name: draft.name,
        description: draft.description || null,
        formula: draft.formula,
        unit: draft.unit || null,
        category: draft.category,
        is_additional: draft.additional,
        green_threshold: draft.green === "" ? null : Number(draft.green),
        yellow_threshold: draft.yellow === "" ? null : Number(draft.yellow),
      });
      onSaved(draft.code);
    } catch (err) {
      setError(errorMessage(err));
    }
  }
  return (
    <Modal
      title="Nuevo KPI"
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            Cancelar
          </button>
          <button className="btn pri" disabled={!draft.code || !draft.name || !draft.formula} onClick={() => void save()}>
            Crear
          </button>
        </>
      }
    >
      <div className="row">
        <Field label="Código">
          <input value={draft.code} onChange={set("code")} placeholder="P09" />
        </Field>
        <Field label="Categoría">
          <select value={draft.category} onChange={set("category")}>
            <option value="PROYECTO">Proyecto e hitos</option>
            <option value="CAMBIO">Gestión del cambio</option>
          </select>
        </Field>
        <Field label="Unidad">
          <input value={draft.unit} onChange={set("unit")} placeholder="%, índice, CLP, días" />
        </Field>
      </div>
      <Field label="Nombre">
        <input value={draft.name} onChange={set("name")} />
      </Field>
      <Field label="Descripción">
        <input value={draft.description} onChange={set("description")} />
      </Field>
      <Field label="Fórmula" hint={`Variables: ${board.variables.map((variable) => variable.code).slice(0, 18).join(", ")}…`}>
        <input className="mono" value={draft.formula} onChange={set("formula")} placeholder="EAC - BAC" />
      </Field>
      <div className="row">
        <Field label="Umbral verde">
          <input type="number" step="any" value={draft.green} onChange={set("green")} />
        </Field>
        <Field label="Umbral amarillo">
          <input type="number" step="any" value={draft.yellow} onChange={set("yellow")} />
        </Field>
      </div>
      {error && <Alert level="crit">{error}</Alert>}
    </Modal>
  );
}
