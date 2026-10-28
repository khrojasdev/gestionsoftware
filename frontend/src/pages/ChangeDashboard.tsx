import { api } from "../api";
import { Alert, Card, ErrorBox, Loading, PageHeader, Tag, useLoad } from "../components/ui";
import { d, KPI_LABEL, kpiDot, kpiTag, kpiValue, moneyM, n, pct, statusTag } from "../format";
import { useProject } from "../project";
import { href } from "../router";
import type { ChangeDashboard } from "../types";

const LEVELS_I = ["ALTO", "MEDIO", "BAJO"] as const;
const LEVELS_P = ["BAJA", "MEDIA", "ALTA"] as const;
const CELL: Record<string, string> = {
  "ALTO-ALTA": "#f3c9c2",
  "ALTO-MEDIA": "#f6d9d3",
  "MEDIO-ALTA": "#f6d9d3",
  "ALTO-BAJA": "#fbefd2",
  "MEDIO-MEDIA": "#fbefd2",
  "BAJO-ALTA": "#fbefd2",
  "MEDIO-BAJA": "#dcf0e3",
  "BAJO-MEDIA": "#dcf0e3",
  "BAJO-BAJA": "#e8f5ec",
};

export default function ChangeDashboardPage() {
  const { projectId, version } = useProject();
  const { data, error, loading, reload } = useLoad(() => api.get<ChangeDashboard>(`/projects/${projectId}/dashboard/change`), [projectId, version]);
  if (loading && !data) return <Loading />;
  if (error || !data) return <ErrorBox error={error ?? "Sin datos"} onRetry={() => void reload()} />;
  const m = data.metrics;
  const maxFunnel = Math.max(...data.funnel.map((row) => row.count), 1);
  const maxTime = Math.max(...data.stage_times.map((row) => Math.max(row.avg_days ?? 0, row.sla_days ?? 0)), 1);
  const kpis = Object.entries(data.kpis);
  const base = kpis.filter(([, item]) => !item.is_additional);
  const extra = kpis.filter(([, item]) => item.is_additional);

  return (
    <>
      <PageHeader crumb="Tableros" title="Tablero de gestión del cambio">
        <span className="cut">
          Datos a la fecha de corte <b className="mono">{d(data.cutoff)}</b>
        </span>
      </PageHeader>
      <div className="grid g6" style={{ marginBottom: 16 }}>
        <Tile label="Solicitudes" value={n(m.CHANGE_REQUESTS)} sub={Object.entries(data.by_status).map(([key, value]) => `${value} ${key.toLowerCase()}`).join(" · ")} />
        <Tile label="Tasa de aprobación" value={pct(m.CHANGE_APPROVAL_RATE * 100)} sub={`Rechazo ${pct(m.CHANGE_REJECTION_RATE * 100)}`} />
        <Tile label="Tiempo medio de ciclo" value={`${n(m.CHANGE_AVG_CYCLE_HOURS / 24, 1)} días`} sub={`Evaluación de impacto ${n(m.CHANGE_AVG_IMPACT_HOURS / 24, 1)} d`} status={data.kpis.C04?.status} />
        <Tile label="Impacto acumulado aprobado" value={moneyM(m.CHANGE_IMPACT_COST)} sub={`${n(m.CHANGE_IMPACT_DAYS)} días de plazo`} status={data.kpis.C06?.status} />
        <Tile label="Contingencia consumida" value={pct(m.CHANGE_CONTINGENCY_CONSUMPTION, 1)} sub={`de ${moneyM(data.contingency_amount)}`} status={data.kpis.C10?.status} />
        <Tile label="Fuera de SLA" value={n(m.CHANGE_SLA_BREACHES)} sub={`Evidencia completa ${pct(m.CHANGE_EVIDENCE_COMPLETE_PCT * 100)}`} status={data.kpis.C09?.status} />
      </div>
      <div className="grid g3" style={{ marginBottom: 16 }}>
        <Card title="Embudo por etapa (solicitudes en curso)">
          <div className="funnel">
            {data.funnel.map((row) => (
              <div className="r" key={row.sequence}>
                <span className="lbl-n">{row.sequence}</span>
                <div className="b" title={`${row.name}: ${row.count}`}>
                  <i style={{ width: `${(row.count / maxFunnel) * 100}%` }} />
                  <span style={{ color: row.count ? "#fff" : "var(--muted)" }}>{row.name}</span>
                </div>
                <span className="mono" style={{ fontSize: 12 }}>
                  {row.count}
                </span>
              </div>
            ))}
          </div>
        </Card>
        <Card title="Tiempo promedio por etapa vs SLA (días)">
          <div className="bars-h">
            {data.stage_times.map((row) => (
              <div className="r" key={row.sequence} style={{ gridTemplateColumns: "130px 1fr 60px" }}>
                <span className="ell" title={row.name}>
                  {row.sequence}. {row.name}
                </span>
                <div className="tr">
                  {row.sla_days !== null && <div className="p" style={{ width: `${(row.sla_days / maxTime) * 100}%` }} />}
                  {row.avg_days !== null && <div className={`a ${row.sla_days !== null && row.avg_days > row.sla_days ? "late" : ""}`} style={{ width: `${(row.avg_days / maxTime) * 100}%` }} />}
                </div>
                <span className="mono" style={{ fontSize: 11.5, textAlign: "right" }}>
                  {row.avg_days !== null ? n(row.avg_days, 1) : "—"}
                  <span className="muted">/{row.sla_days !== null ? n(row.sla_days, 1) : "—"}</span>
                </span>
              </div>
            ))}
          </div>
          <div className="legend" style={{ border: 0, padding: "4px 0 0" }}>
            <span>
              <i className="lg" style={{ background: "var(--plan)" }} /> SLA
            </span>
            <span>
              <i className="lg" style={{ background: "var(--real)" }} /> Promedio real
            </span>
            <span>
              <i className="lg" style={{ background: "var(--warn)" }} /> Sobre SLA
            </span>
          </div>
        </Card>
        <Card title="Matriz impacto × probabilidad">
          <div className="matrix">
            {LEVELS_I.map((impact) => (
              <div key={impact} style={{ display: "contents" }}>
                <div className="ax" style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}>
                  {impact[0] + impact.slice(1).toLowerCase()}
                </div>
                {LEVELS_P.map((probability) => (
                  <div key={probability} className="cell" style={{ background: CELL[`${impact}-${probability}`] }}>
                    {data.risk
                      .filter((row) => row.impact === impact && row.probability === probability)
                      .map((row) => (
                        <a key={row.code} className="pin" href={href("cambio", data.requests.find((request) => request.code === row.code)?.id ?? "")} title={`${row.title} (${row.status.toLowerCase()})`}>
                          {row.code}
                        </a>
                      ))}
                  </div>
                ))}
              </div>
            ))}
            <div />
            {LEVELS_P.map((probability) => (
              <div key={probability} className="ax">
                {probability[0] + probability.slice(1).toLowerCase()}
              </div>
            ))}
          </div>
          <p className="muted" style={{ fontSize: 11.5, margin: "8px 0 0" }}>
            Impacto según plazo y costo simulados; probabilidad según prioridad y etapa alcanzada.
          </p>
        </Card>
      </div>
      <div className="grid" style={{ gridTemplateColumns: "minmax(0,1.4fr) minmax(0,1fr)", marginBottom: 16 }}>
        <Card title="KPI de gestión del cambio" actions={<a href={href("kpi")}>Ver fórmulas →</a>}>
          <div className="kpi-grid">
            {base.map(([code, item]) => (
              <a key={code} className="kpi-mini" href={href("kpi", code)}>
                <span className="l">
                  <span className={`dot ${kpiDot(item.status)}`} /> <span className="mono">{code}</span> {item.name}
                </span>
                <b>{kpiValue(item.value, item.unit)}</b>
                <Tag cls={kpiTag(item.status)}>{KPI_LABEL[item.status]}</Tag>
              </a>
            ))}
          </div>
          {extra.length > 0 && (
            <>
              <h4 className="h4" style={{ marginTop: 14 }}>
                KPI adicionales propuestos por el equipo
              </h4>
              <div className="kpi-grid">
                {extra.map(([code, item]) => (
                  <a key={code} className="kpi-mini extra" href={href("kpi", code)}>
                    <span className="l">
                      <span className={`dot ${kpiDot(item.status)}`} /> <span className="mono">{code}</span> {item.name}
                    </span>
                    <b>{kpiValue(item.value, item.unit)}</b>
                    <Tag cls={kpiTag(item.status)}>{KPI_LABEL[item.status]}</Tag>
                  </a>
                ))}
              </div>
            </>
          )}
        </Card>
        <Card title="Alertas">
          <div className="grid" style={{ gap: 8 }}>
            {data.alerts.map((alert, index) => (
              <Alert key={index} level={alert.level}>
                {alert.text}
              </Alert>
            ))}
            {!data.alerts.length && <Alert level="ok">Sin alertas.</Alert>}
          </div>
          <h4 className="h4" style={{ marginTop: 14 }}>
            Por tipo
          </h4>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {Object.entries(data.by_type).map(([key, value]) => (
              <span key={key} className="chip">
                {key} <b>{value}</b>
              </span>
            ))}
          </div>
        </Card>
      </div>
      <Card title="Solicitudes" bodyClass="card-b scroll">
        <table className="t">
          <thead>
            <tr>
              <th>Código</th>
              <th>Título</th>
              <th>Etapa</th>
              <th className="num">Plazo</th>
              <th className="num">Costo</th>
              <th>Estado</th>
            </tr>
          </thead>
          <tbody>
            {data.requests.map((row) => (
              <tr key={row.id}>
                <td className="mono">
                  <a href={href("cambio", row.id)}>{row.code}</a>
                </td>
                <td>{row.title}</td>
                <td style={{ fontSize: 12.5 }}>
                  {row.stage_sequence}. {row.stage_name} {row.sla_breached && <Tag cls="t-crit">SLA</Tag>}
                </td>
                <td className="num mono">{row.delta_days !== null ? `${row.delta_days > 0 ? "+" : ""}${row.delta_days} d` : "—"}</td>
                <td className="num mono">{row.delta_cost !== null ? moneyM(row.delta_cost) : "—"}</td>
                <td>
                  <Tag cls={statusTag(row.status)}>{row.status_label}</Tag>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </>
  );
}

function Tile({ label, value, sub, status }: { label: string; value: string; sub?: string; status?: string }) {
  const dot = status ? kpiDot(status as never) : "";
  return (
    <div className="card kpi">
      <div className="l">
        {dot && <span className={`dot ${dot}`} />}
        {label}
      </div>
      <div className="v" style={{ fontSize: 21 }}>
        {value}
      </div>
      {sub && <div className="s">{sub}</div>}
    </div>
  );
}
