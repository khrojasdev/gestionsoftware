import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";

import { errorMessage } from "../api";
import { d, money, signed } from "../format";
import type { Change, ProjectFinish } from "../types";

/* ------------------------------------------------------------ data hook */
// eslint-disable-next-line react-refresh/only-export-components
export function useLoad<T>(loader: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const loaderRef = useRef(loader);
  useLayoutEffect(() => {
    loaderRef.current = loader;
  });
  const counter = useRef(0);

  const reload = useCallback(async () => {
    const id = ++counter.current;
    setLoading(true);
    try {
      const value = await loaderRef.current();
      if (id === counter.current) {
        setData(value);
        setError(null);
      }
    } catch (err) {
      if (id === counter.current) setError(errorMessage(err));
    } finally {
      if (id === counter.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Data fetching: the loading flag is set synchronously on purpose.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, error, loading, reload, setData };
}

/* ------------------------------------------------------------ toasts */
type Toast = { id: number; kind: "ok" | "crit" | "warn" | "info"; text: ReactNode };
const ToastContext = createContext<(kind: Toast["kind"], text: ReactNode) => void>(() => undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((kind: Toast["kind"], text: ReactNode) => {
    const id = Date.now() + Math.random();
    setToasts((list) => [...list, { id, kind, text }]);
    setTimeout(() => setToasts((list) => list.filter((toast) => toast.id !== id)), kind === "crit" ? 9000 : 5500);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((toast) => (
          <div key={toast.id} className={`alert ${toast.kind} toast`} onClick={() => setToasts((list) => list.filter((t) => t.id !== toast.id))}>
            <Icon name={toast.kind === "ok" ? "check" : toast.kind === "info" ? "info" : "alert"} />
            <div>{toast.text}</div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useToast() {
  return useContext(ToastContext);
}

/* ------------------------------------------------------------ icons */
const PATHS: Record<string, string> = {
  check: "M3 8.5l3 3 7-7",
  alert: "M8 2l6.5 11.5h-13L8 2zm0 4.5v3.2m0 2v.1",
  info: "M8 1.8a6.2 6.2 0 100 12.4A6.2 6.2 0 008 1.8zm0 5v4.4m0-6.3v.1",
  plus: "M8 3v10M3 8h10",
  upload: "M8 11V3m-3.5 3.5L8 3l3.5 3.5M3 13h10",
  download: "M8 3v8m-3.5-3.5L8 11l3.5-3.5M3 13h10",
  x: "M4 4l8 8M12 4l-8 8",
  edit: "M10.5 2.5l3 3L6 13H3v-3l7.5-7.5z",
  file: "M4 1.8h5.2L12.5 5v9.2h-8.5V1.8zM9 1.8V5h3.5",
  trash: "M3 4.5h10M6.5 4.5V3h3v1.5m-5 0l.6 9h5.8l.6-9",
  arrow: "M3 8h10m-3.5-3.5L13 8l-3.5 3.5",
  logout: "M6 3H3v10h3m4-8l3 3-3 3m3-3H6",
  play: "M5 3l8 5-8 5V3z",
  refresh: "M13 8a5 5 0 11-1.5-3.6M13 2.5v2.5h-2.5",
};

export function Icon({ name, size = 16 }: { name: string; size?: number }) {
  return (
    <svg className="ico" width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={PATHS[name] ?? PATHS.info} />
    </svg>
  );
}

/* ------------------------------------------------------------ layout pieces */
export function PageHeader({ crumb, title, children }: { crumb: string; title: string; children?: ReactNode }) {
  return (
    <div className="sh">
      <div>
        <div className="crumb">{crumb}</div>
        <h1>{title}</h1>
      </div>
      <div className="sp" />
      {children}
    </div>
  );
}

export function Card({ title, actions, children, className = "", bodyClass = "card-b", id }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; bodyClass?: string; id?: string }) {
  return (
    <section className={`card ${className}`} id={id}>
      {title !== undefined && (
        <div className="card-h">
          <h3>{title}</h3>
          <div className="sp" />
          {actions}
        </div>
      )}
      <div className={bodyClass}>{children}</div>
    </section>
  );
}

export function Loading({ text = "Cargando…" }: { text?: string }) {
  return (
    <div className="loading">
      <span className="spinner" />
      {text}
    </div>
  );
}

export function ErrorBox({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <div className="alert crit" role="alert">
      <Icon name="alert" />
      <div style={{ flex: 1 }}>{error}</div>
      {onRetry && (
        <button className="btn sm" onClick={onRetry}>
          Reintentar
        </button>
      )}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Tag({ cls, children, title }: { cls: string; children: ReactNode; title?: string }) {
  return (
    <span className={`tag ${cls}`} title={title}>
      {children}
    </span>
  );
}

export function Bar({ value, cls = "", plan }: { value: number; cls?: string; plan?: number }) {
  return (
    <div className="bar barx" title={plan !== undefined ? `Real ${Math.round(value)} % · Plan ${Math.round(plan)} %` : `${Math.round(value)} %`}>
      <i className={cls} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
      {plan !== undefined && <b style={{ left: `${Math.max(0, Math.min(100, plan))}%` }} />}
    </div>
  );
}

export function Alert({ level, children }: { level: "crit" | "warn" | "ok" | "info"; children: ReactNode }) {
  return (
    <div className={`alert ${level}`}>
      <Icon name={level === "ok" ? "check" : level === "info" ? "info" : "alert"} />
      <div>{children}</div>
    </div>
  );
}

export function ReadOnlyNote({ children }: { children?: ReactNode }) {
  return (
    <div className="alert info ro">
      <Icon name="info" />
      <div>{children ?? "Vista de consulta: tu rol no permite modificar esta información."}</div>
    </div>
  );
}

/* ------------------------------------------------------------ modal */
export function Modal({ title, onClose, children, footer, wide = false }: { title: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, [onClose]);
  return (
    <div className="modal-bg" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className={`card modal ${wide ? "wide" : ""}`} role="dialog" aria-modal="true">
        <div className="card-h">
          <h3>{title}</h3>
          <div className="sp" />
          <button className="btn sm" onClick={onClose} aria-label="Cerrar">
            <Icon name="x" size={14} />
          </button>
        </div>
        <div className="card-b">{children}</div>
        {footer && <div className="modal-f">{footer}</div>}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------ before/after table */
export function ChangesTable({ changes, limit = 14 }: { changes: Change[]; limit?: number }) {
  if (!changes.length) return <p className="muted">No hubo cambios en fechas, duraciones ni costos.</p>;
  return (
    <div className="scroll" style={{ maxHeight: 340 }}>
      <table className="t">
        <thead>
          <tr>
            <th>ID</th>
            <th>Elemento</th>
            <th>Inicio</th>
            <th>Término</th>
            <th className="num">Duración</th>
            <th className="num">Costo</th>
          </tr>
        </thead>
        <tbody>
          {changes.slice(0, limit).map((row) => (
            <tr key={row.external_id}>
              <td className="mono">{row.external_id}</td>
              <td style={{ maxWidth: 280 }} className="ell">
                {row.name}
              </td>
              <td className="mono">
                <BeforeAfter before={d(row.start_before)} after={d(row.start_after)} />
              </td>
              <td className="mono">
                <BeforeAfter before={d(row.finish_before)} after={d(row.finish_after)} />
              </td>
              <td className="num mono">
                <BeforeAfter before={row.duration_before ?? "—"} after={row.duration_after ?? "—"} />
              </td>
              <td className="num mono">
                <BeforeAfter before={money(row.cost_before)} after={money(row.cost_after)} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {changes.length > limit && <p className="muted" style={{ fontSize: 12 }}>… y {changes.length - limit} elementos más.</p>}
    </div>
  );
}

export function BeforeAfter({ before, after }: { before: ReactNode; after: ReactNode }) {
  if (String(before) === String(after)) return <span className="muted">{after}</span>;
  return (
    <span className="ba-inline">
      <s>{before}</s> <b>{after}</b>
    </span>
  );
}

function shift(label: string, before: string | null, after: string | null) {
  if (!before || !after) return null;
  if (before === after)
    return (
      <div>
        {label}: se mantiene en <b className="mono">{d(after)}</b>
      </div>
    );
  const days = Math.round((Date.parse(after) - Date.parse(before)) / 86_400_000);
  return (
    <div>
      {label}: <span className="mono">{d(before)}</span> → <b className="mono">{d(after)}</b> ({signed(days, " días corridos")})
    </div>
  );
}

export function FinishShift({ before, after }: { before: ProjectFinish | null; after: ProjectFinish | null }) {
  if (!before || !after) return null;
  return (
    <>
      {shift("Término planificado del proyecto", before.plan, after.plan)}
      {shift("Término proyectado (con avance real)", before.forecast, after.forecast)}
    </>
  );
}

/* ------------------------------------------------------------ small inputs */
export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <div className="field">
      <label>{label}</label>
      {children}
      {hint && <small className="muted">{hint}</small>}
    </div>
  );
}

export function Seg<T extends string>({ value, options, onChange }: { value: T; options: { value: T; label: ReactNode }[]; onChange: (value: T) => void }) {
  return (
    <div className="role seg">
      {options.map((option) => (
        <button key={option.value} type="button" className={option.value === value ? "on" : ""} onClick={() => onChange(option.value)}>
          {option.label}
        </button>
      ))}
    </div>
  );
}
