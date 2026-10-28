import { useState, type FormEvent } from "react";

import { errorMessage } from "../api";
import { useAuth } from "../auth";
import { Alert } from "../components/ui";

const DEMO = [
  { email: "admin@trazo.cl", role: "Administrador", text: "Gestiona usuarios y roles, crea y elimina proyectos; tiene todos los permisos." },
  { email: "kevin.henriquez@trazo.cl", role: "Jefe de Proyecto", text: "Importa la Carta Gantt, edita duraciones, precedencias y recursos, configura KPI y aprueba cambios." },
  { email: "diego.lopez@trazo.cl", role: "Integrante del equipo", text: "Registra avance de sus tareas, crea solicitudes de cambio y consulta Gantt y tableros." },
];
const DEMO_PASSWORD = "Trazo2026!";

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState(DEMO[1].email);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <div className="card login">
        <div className="art">
          <div className="brand" style={{ padding: 0 }}>
            <div className="brand-mark">
              <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
                <path d="M2 4h10M2 9h14M2 14h7" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" />
              </svg>
            </div>
            <div>
              <b>Trazo</b>
              <small>Planificación y control</small>
            </div>
          </div>
          <h2>De la Carta Gantt al control del proyecto, con cada cambio trazado.</h2>
          <p>Importa la planificación, ajusta precedencias y recursos, y controla el proyecto con KPI, hitos y gestión del cambio en un solo lugar.</p>
          <svg viewBox="0 0 420 170" className="art-svg" aria-hidden="true">
            <g fontFamily="IBM Plex Mono, monospace" fontSize="9" fill="#7f8992">
              <text x="0" y="12">A16</text>
              <text x="0" y="42">A17</text>
              <text x="0" y="72">A18</text>
              <text x="0" y="102">A19</text>
              <text x="0" y="132">H05</text>
            </g>
            <rect x="34" y="4" width="110" height="10" rx="2" fill="#2e7d6b" />
            <rect x="120" y="34" width="150" height="10" rx="2" fill="#c23b2c" />
            <rect x="150" y="64" width="120" height="10" rx="2" fill="#2e7d6b" opacity=".7" />
            <rect x="250" y="94" width="110" height="10" rx="2" fill="#4b5560" />
            <path d="M144 9h8v30h-30" stroke="#7f8992" fill="none" />
            <path d="M270 39h8v30" stroke="#c23b2c" fill="none" />
            <rect x="196" y="0" width="2" height="150" fill="#d96a17" />
            <rect x="364" y="125" width="10" height="10" transform="rotate(45 369 130)" fill="#d96a17" />
          </svg>
        </div>
        <form className="form" onSubmit={submit}>
          <h2 style={{ margin: "0 0 4px", fontSize: 21 }}>Ingresar</h2>
          <p className="muted" style={{ margin: "0 0 18px" }}>
            Usa tu correo y contraseña. El rol lo asigna el administrador.
          </p>
          <div className="field">
            <label htmlFor="email">Correo</label>
            <input id="email" type="email" autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} required />
          </div>
          <div className="field">
            <label htmlFor="password">Contraseña</label>
            <input id="password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required />
          </div>
          {error && <Alert level="crit">{error}</Alert>}
          <button className="btn pri" style={{ justifyContent: "center", marginTop: 10, padding: "10px 12px" }} disabled={busy}>
            {busy ? "Ingresando…" : "Ingresar"}
          </button>
          <div className="demo-box">
            <div className="muted" style={{ fontSize: 12, margin: "18px 0 8px" }}>
              Cuentas de demostración (contraseña <span className="mono">{DEMO_PASSWORD}</span>) · un clic completa el formulario
            </div>
            {DEMO.map((item) => (
              <label key={item.email} className={`rolecard ${email === item.email ? "on" : ""}`}>
                <input
                  type="radio"
                  name="demo"
                  checked={email === item.email}
                  onChange={() => {
                    setEmail(item.email);
                    setPassword(DEMO_PASSWORD);
                  }}
                />
                <div>
                  <b>{item.role}</b> <span className="mono muted">{item.email}</span>
                  <br />
                  <span className="muted">{item.text}</span>
                </div>
              </label>
            ))}
          </div>
        </form>
      </div>
    </div>
  );
}
