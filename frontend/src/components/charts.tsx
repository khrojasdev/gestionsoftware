import { useState } from "react";

import { d, dShort, moneyM } from "../format";

/** Small trend line for KPI history. */
export function Sparkline({ points, width = 260, height = 70, green, yellow }: { points: { cutoff: string; value: number | null }[]; width?: number; height?: number; green?: number | null; yellow?: number | null }) {
  const values = points.filter((point) => point.value !== null) as { cutoff: string; value: number }[];
  if (values.length < 2) return <p className="muted" style={{ fontSize: 12 }}>Aún no hay suficientes mediciones para graficar la tendencia.</p>;
  const all = values.map((point) => point.value);
  [green, yellow].forEach((value) => value !== null && value !== undefined && all.push(value));
  let min = Math.min(...all);
  let max = Math.max(...all);
  if (min === max) {
    min -= 1;
    max += 1;
  }
  const pad = (max - min) * 0.12;
  min -= pad;
  max += pad;
  const sx = (index: number) => 8 + (index / (values.length - 1)) * (width - 16);
  const sy = (value: number) => height - 16 - ((value - min) / (max - min)) * (height - 26);
  const path = values.map((point, index) => `${index ? "L" : "M"}${sx(index).toFixed(1)} ${sy(point.value).toFixed(1)}`).join(" ");
  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`} className="spark" role="img" aria-label="Tendencia del KPI">
      {green !== null && green !== undefined && <line x1="0" x2={width} y1={sy(green)} y2={sy(green)} stroke="var(--ok)" strokeDasharray="3 3" strokeWidth="1" />}
      {yellow !== null && yellow !== undefined && <line x1="0" x2={width} y1={sy(yellow)} y2={sy(yellow)} stroke="var(--warn)" strokeDasharray="3 3" strokeWidth="1" />}
      <path d={path} fill="none" stroke="var(--ink)" strokeWidth="1.8" />
      {values.map((point, index) => (
        <circle key={point.cutoff} cx={sx(index)} cy={sy(point.value)} r={index === values.length - 1 ? 3.5 : 2} fill={index === values.length - 1 ? "var(--accent)" : "var(--ink)"}>
          <title>
            {d(point.cutoff)}: {point.value.toFixed(2)}
          </title>
        </circle>
      ))}
      <text x="4" y={height - 2} fontSize="9" fill="var(--muted)" fontFamily="var(--mono)">
        {dShort(values[0].cutoff)}
      </text>
      <text x={width - 4} y={height - 2} fontSize="9" fill="var(--muted)" textAnchor="end" fontFamily="var(--mono)">
        {dShort(values[values.length - 1].cutoff)}
      </text>
    </svg>
  );
}

/** Earned-value S curve (PV, EV, AC) with the cutoff marker. */
export function SCurve({ points, cutoff }: { points: { date: string; pv: number; ev: number | null; ac: number | null }[]; cutoff: string | null }) {
  const [hover, setHover] = useState<number | null>(null);
  if (!points.length) return null;
  const width = 640;
  const height = 240;
  const left = 54;
  const bottom = 26;
  const max = Math.max(...points.flatMap((point) => [point.pv, point.ev ?? 0, point.ac ?? 0])) * 1.06;
  const t0 = Date.parse(points[0].date);
  const t1 = Date.parse(points[points.length - 1].date);
  const sx = (date: string) => left + ((Date.parse(date) - t0) / Math.max(1, t1 - t0)) * (width - left - 12);
  const sy = (value: number) => height - bottom - (value / max) * (height - bottom - 10);
  const line = (key: "pv" | "ev" | "ac") =>
    points
      .filter((point) => point[key] !== null && point[key] !== undefined)
      .map((point, index) => `${index ? "L" : "M"}${sx(point.date).toFixed(1)} ${sy(point[key] as number).toFixed(1)}`)
      .join(" ");
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((ratio) => ratio * max);
  const active = hover !== null ? points[hover] : null;
  return (
    <div style={{ position: "relative" }}>
      <svg width="100%" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Curva S de valor planificado, ganado y costo real" onMouseLeave={() => setHover(null)}>
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={left} x2={width - 8} y1={sy(tick)} y2={sy(tick)} stroke="var(--line-2)" />
            <text x={left - 6} y={sy(tick) + 3} fontSize="9.5" textAnchor="end" fill="var(--muted)" fontFamily="var(--mono)">
              {moneyM(tick).replace(" M", "M")}
            </text>
          </g>
        ))}
        {points.map((point, index) => (
          <text key={point.date} x={sx(point.date)} y={height - 8} fontSize="9.5" textAnchor="middle" fill="var(--muted)" fontFamily="var(--mono)">
            {index % Math.ceil(points.length / 8) === 0 || index === points.length - 1 ? point.date.slice(5, 7) + "/" + point.date.slice(2, 4) : ""}
          </text>
        ))}
        {cutoff && Date.parse(cutoff) >= t0 && Date.parse(cutoff) <= t1 && (
          <g>
            <line x1={sx(cutoff)} x2={sx(cutoff)} y1={6} y2={height - bottom} stroke="var(--accent)" strokeWidth="1.5" />
            <text x={sx(cutoff) + 4} y={14} fontSize="9.5" fill="var(--accent-ink)" fontFamily="var(--mono)">
              corte {dShort(cutoff)}
            </text>
          </g>
        )}
        <path d={line("pv")} fill="none" stroke="#8a9198" strokeWidth="2" strokeDasharray="5 4" />
        <path d={line("ac")} fill="none" stroke="var(--crit)" strokeWidth="2" />
        <path d={line("ev")} fill="none" stroke="var(--real)" strokeWidth="2.4" />
        {points.map((point, index) => (
          <rect key={point.date} x={sx(point.date) - 12} y={0} width={24} height={height - bottom} fill="transparent" onMouseEnter={() => setHover(index)} />
        ))}
        {active && <line x1={sx(active.date)} x2={sx(active.date)} y1={6} y2={height - bottom} stroke="var(--ink)" strokeOpacity=".25" />}
      </svg>
      {active && (
        <div className="chart-tip" style={{ left: `${(sx(active.date) / width) * 100}%` }}>
          <b>{d(active.date)}</b>
          <span>PV {moneyM(active.pv)}</span>
          {active.ev != null && <span>EV {moneyM(active.ev)}</span>}
          {active.ac != null && <span>AC {moneyM(active.ac)}</span>}
        </div>
      )}
      <div className="legend" style={{ border: 0, padding: "4px 0 0" }}>
        <span>
          <i className="lg" style={{ background: "repeating-linear-gradient(90deg,#8a9198 0 5px,transparent 5px 9px)", height: 3 }} /> PV · valor planificado
        </span>
        <span>
          <i className="lg" style={{ background: "var(--real)", height: 3 }} /> EV · valor ganado
        </span>
        <span>
          <i className="lg" style={{ background: "var(--crit)", height: 3 }} /> AC · costo real
        </span>
      </div>
    </div>
  );
}
