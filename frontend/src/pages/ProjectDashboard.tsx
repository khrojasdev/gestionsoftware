import { api } from "../api";
import { SCurve } from "../components/charts";
import { Alert, Card, ErrorBox, Loading, PageHeader, Tag, useLoad } from "../components/ui";
import { d, dShort, KPI_LABEL, kpiDot, kpiTag, kpiValue, moneyM, n, pct, statusTag } from "../format";
import { useProject } from "../project";
import { href } from "../router";
import type { ProjectDashboard } from "../types";

export default function ProjectDashboardPage() {
  const { projectId, version } = useProject();
  const { data, error, loading, reload } = useLoad(() => api.get<ProjectDashboard>(`/projects/${projectId}/dashboard/project`), [projectId, version]);
  if (loading && !data) return <Loading />;
  if (error || !data) return <ErrorBox error={error ?? "Sin datos"} onRetry={() => void reload()} />;
  const m = data.metrics;
  const slip = data.finish.forecast && data.finish.baseline ? Math.round((Date.parse(data.finish.forecast) - Date.parse(data.finish.baseline)) / 86_400_000) : 0;
  const kpi = (code: string) => data.kpis[code];

  return (
    <>
      <PageHeader crumb="Tableros" title={`Tablero del proyecto · ${data.project.name}`}>
        <span className="cut">
          Datos a la fecha de corte <b className="mono">{d(data.cutoff)}</b>
        </span>
      </PageHeader>
      <div className="grid g6" style={{ marginBottom: 16 }}>
        <Tile label="Avance real" value={pct(m.AVANCE_REAL, 1)} sub={`Plan ${pct(m.AVANCE_PLAN, 1)} · ${n(m.AVANCE_REAL - m.AVANCE_PLAN, 1)} pp`} status={kpi("P05")?.status} />
        <Tile label="SPI · cronograma" value={n(m.SPI, 2)} sub={`SV ${moneyM(m.SV)}`} status={kpi("P01")?.status} />
        <Tile label="CPI · costo" value={n(m.CPI, 2)} sub={`CV ${moneyM(m.CV)}`} status={kpi("P02")?.status} />
        <Tile label="EAC · costo estimado al término" value={moneyM(m.EAC)} sub={`BAC ${moneyM(m.BAC)} · VAC ${moneyM(m.VAC)}`} status={m.VAC < 0 ? "AMARILLO" : "VERDE"} />
        <Tile
          label="Término proyectado"
          value={d(data.finish.forecast)}
          sub={`Base ${dShort(data.finish.baseline)} (${slip >= 0 ? "+" : ""}${slip} días corridos) · reserva ${data.reserve_days ?? "—"} días hábiles`}
          status={(data.reserve_days ?? 0) < 0 ? "ROJO" : slip > 0 ? "AMARILLO" : "VERDE"}
        />
        <Tile label="Hitos cumplidos" value={`${data.milestones_done}/${data.milestones_total}`} sub={`${pct(m.MILESTONES_ON_TIME_PCT)} a tiempo · ${data.late_count} tareas atrasadas`} status={kpi("P07")?.status} />
      </div>
      <div className="grid" style={{ gridTemplateColumns: "minmax(0,1.6fr) minmax(0,1fr)", marginBottom: 16 }}>
        <Card title="Curva S · valor planificado, ganado y costo real">
          <SCurve points={data.curve} cutoff={data.cutoff} />
        </Card>
        <Card title="Alertas">
          <div className="grid" style={{ gap: 8 }}>
            {data.alerts.map((alert, index) => (
              <Alert key={index} level={alert.level}>
                {alert.text}
              </Alert>
            ))}
            {!data.alerts.length && <Alert level="ok">Sin alertas a la fecha de corte.</Alert>}
          </div>
        </Card>
      </div>
      <div className="grid g2" style={{ marginBottom: 16 }}>
        <Card title="Avance por etapa (plan vs real)">
          <div className="bars-h">
            {data.stages.map((stage) => (
              <div className="r" key={stage.external_id} title={`${stage.name}: real ${Math.round(stage.progress)} % · plan ${Math.round(stage.planned_pct)} %`} style={{ gridTemplateColumns: "190px 1fr 72px" }}>
                <span className="ell">
                  <span className="mono muted">{stage.external_id}</span> {stage.name}
                </span>
                <div className="tr">
                  <div className="p" style={{ width: `${Math.min(100, stage.planned_pct)}%` }} />
                  <div className={`a ${stage.progress + 0.5 < stage.planned_pct ? "late" : ""}`} style={{ width: `${Math.min(100, stage.progress)}%` }} />
                </div>
                <span className="mono" style={{ fontSize: 12, textAlign: "right" }}>
                  {Math.round(stage.progress)}% <span className="muted">/{Math.round(stage.planned_pct)}</span>
                </span>
              </div>
            ))}
          </div>
          <div className="legend" style={{ border: 0, padding: "4px 0 0" }}>
            <span>
              <i className="lg" style={{ background: "var(--plan)" }} /> Planificado a la fecha de corte
            </span>
            <span>
              <i className="lg" style={{ background: "var(--real)" }} /> Real
            </span>
            <span>
              <i className="lg" style={{ background: "var(--warn)" }} /> Real bajo lo planificado
            </span>
          </div>
        </Card>
        <Card title="KPI de proyecto e hitos" actions={<a href={href("kpi")}>Ver fórmulas →</a>}>
          <div className="kpi-grid">
            {Object.entries(data.kpis).map(([code, item]) => (
              <a key={code} className="kpi-mini" href={href("kpi", code)}>
                <span className="l">
                  <span className={`dot ${kpiDot(item.status)}`} /> <span className="mono">{code}</span> {item.name}
                </span>
                <b>{kpiValue(item.value, item.unit)}</b>
                <Tag cls={kpiTag(item.status)}>{KPI_LABEL[item.status]}</Tag>
              </a>
            ))}
          </div>
        </Card>
      </div>
      <div className="grid g2">
        <Card title={`Tareas atrasadas o desplazadas (${data.late.length})`} bodyClass="card-b scroll">
          <table className="t">
            <thead>
              <tr>
                <th>Tarea</th>
                <th>Avance</th>
                <th>Término base → proy.</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {data.late.map((row) => (
                <tr key={row.external_id}>
                  <td>
                    <a className="mono" href={href("actividades", row.external_id)}>
                      {row.external_id}
                    </a>{" "}
                    <span style={{ fontSize: 12.5 }}>{row.name}</span> {row.is_critical && <Tag cls="t-crit">Crítica</Tag>}
                  </td>
                  <td className="mono" style={{ fontSize: 12 }}>
                    {Math.round(row.progress)}% / {Math.round(row.planned_pct)}%
                  </td>
                  <td className="mono" style={{ fontSize: 12 }}>
                    {dShort(row.baseline_finish)} → {dShort(row.forecast_finish)} (+{row.slip_days})
                  </td>
                  <td>
                    <Tag cls={statusTag(row.status)}>{row.status_label}</Tag>
                  </td>
                </tr>
              ))}
              {!data.late.length && (
                <tr>
                  <td colSpan={4} className="empty">
                    No hay tareas atrasadas.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </Card>
        <div className="grid">
          <Card title="Hitos">
            <table className="t">
              <thead>
                <tr>
                  <th>Hito</th>
                  <th>Base</th>
                  <th>Proyección</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {data.milestones.map((row) => (
                  <tr key={row.external_id}>
                    <td>
                      <a className="mono" href={href("hitos", row.external_id)}>
                        {row.external_id}
                      </a>{" "}
                      <span style={{ fontSize: 12.5 }}>{row.name}</span>
                    </td>
                    <td className="mono" style={{ fontSize: 12 }}>
                      {d(row.baseline)}
                    </td>
                    <td className="mono" style={{ fontSize: 12, color: row.forecast && row.baseline && row.forecast > row.baseline && row.progress < 100 ? "var(--warn)" : undefined }}>
                      {d(row.forecast)}
                    </td>
                    <td>
                      <Tag cls={row.progress >= 100 ? "t-ok" : row.forecast && row.baseline && row.forecast > row.baseline ? "t-warn" : "t-mute"}>{row.progress >= 100 ? "Cumplido" : row.forecast && row.baseline && row.forecast > row.baseline ? "Desplazado" : "Pendiente"}</Tag>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          <Card title="Carga máxima por profesional" actions={<a href={href("recursos")}>Recursos →</a>}>
            <div className="bars-h">
              {data.load.slice(0, 8).map((row) => (
                <div className="r" key={row.name} style={{ gridTemplateColumns: "190px 1fr 54px" }}>
                  <span className="ell" title={row.name}>
                    {row.name}
                  </span>
                  <div className="tr">
                    <div className="a" style={{ width: `${Math.min(100, row.peak_pct / 2)}%`, background: row.peak_pct > 100 ? "var(--crit)" : undefined, top: 2, bottom: 2 }} />
                    <i className="cap-line" />
                  </div>
                  <span className="mono" style={{ fontSize: 12, textAlign: "right", color: row.peak_pct > 100 ? "var(--crit)" : undefined }}>
                    {Math.round(row.peak_pct)}%
                  </span>
                </div>
              ))}
            </div>
            <p className="muted" style={{ fontSize: 12, margin: 0 }}>
              La línea marca el 100 % de la capacidad diaria; la escala llega a 200 %.
            </p>
          </Card>
        </div>
      </div>
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
