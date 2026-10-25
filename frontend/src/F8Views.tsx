import { useEffect, useState, type FormEvent, type ReactElement } from "react";
import { getCurrentUser, type AuthUser } from "./api";

type User = { id: string; email: string; full_name: string; is_active: boolean; roles: string[]; created_at: string };
type AuditEvent = { id: string; action: string; entity_type: string; occurred_at: string; user_id: string | null };
const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

function manager(user: User): boolean {
  return user.roles.some((role) => ["ADMINISTRADOR", "JEFE_DE_PROYECTO"].includes(role));
}

export function F8App({ onSessionChange }: { onSessionChange?: (token: string | null, user: User | null) => void } = {}): ReactElement {
  const [token, setToken] = useState<string | null>(localStorage.getItem("trazo_token"));
  const [user, setUser] = useState<User | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [email, setEmail] = useState(""); const [password, setPassword] = useState(""); const [error, setError] = useState("");
  useEffect(() => { if (token && !user) void getCurrentUser(token).then((current: AuthUser) => setUser(current as User)).catch(() => { localStorage.removeItem("trazo_token"); setToken(null); }); }, [token, user]);

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(`${API_URL}${path}`, { ...init, headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init.headers } });
    if (!response.ok) { const body = (await response.json().catch(() => ({}))) as { detail?: string }; throw new Error(body.detail ?? "Operación no permitida"); }
    return (await response.json()) as T;
  }

  async function login(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault(); setError("");
    try { const result = await request<{ access_token: string; user: User }>("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }); localStorage.setItem("trazo_token", result.access_token); window.dispatchEvent(new Event("trazo-auth")); setToken(result.access_token); setUser(result.user); onSessionChange?.(result.access_token, result.user); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo iniciar sesión"); }
  }

  async function loadManagement(): Promise<void> {
    if (!user || !manager(user)) return;
    try { const [loadedUsers, loadedEvents] = await Promise.all([request<User[]>("/api/v1/users"), request<AuditEvent[]>("/api/v1/audit-logs")]); setUsers(loadedUsers); setEvents(loadedEvents); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "No se pudo cargar la auditoría"); }
  }

  if (!token || !user) return <section className="section-card f8-panel"><PageTitle /><form onSubmit={login}><h2>Iniciar sesión</h2><input type="email" placeholder="Correo" value={email} onChange={(event) => setEmail(event.target.value)} required /><input type="password" placeholder="Contraseña" value={password} onChange={(event) => setPassword(event.target.value)} minLength={8} required /><button className="btn btn-primary">Entrar</button>{error && <p className="error">{error}</p>}</form></section>;
  return <section className="section-card f8-panel"><PageTitle /><div className="f8-session"><strong>{user.full_name}</strong><span>{user.roles.join(", ")}</span><button className="btn" onClick={() => { localStorage.removeItem("trazo_token"); setToken(null); setUser(null); window.dispatchEvent(new Event("trazo-auth")); onSessionChange?.(null, null); }}>Salir</button></div>{!manager(user) ? <div className="access-denied"><strong>Permisos de integrante</strong><p>Solo puedes registrar avance y fechas reales de tus tareas, crear cambios y consultar el proyecto.</p></div> : <><button className="btn btn-primary" onClick={loadManagement}>Cargar usuarios y auditoría</button><div className="f8-columns"><div><h2>Usuarios y roles</h2><ul>{users.map((item) => <li key={item.id}><strong>{item.full_name}</strong> · {item.email} · {item.roles.join(", ")}</li>)}</ul></div><div><h2>Auditoría</h2><ul>{events.map((item) => <li key={item.id}><strong>{item.action}</strong> · {item.entity_type} · {new Date(item.occurred_at).toLocaleString("es-CL")}</li>)}</ul></div></div></>}{error && <p className="error">{error}</p>}</section>;
}

function PageTitle(): ReactElement { return <><p className="eyebrow">F8 · Seguridad y trazabilidad</p><h1>Usuarios, roles y auditoría</h1><p>La interfaz refleja las mismas restricciones que valida el backend.</p></>; }
