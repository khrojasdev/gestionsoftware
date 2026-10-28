import { useState } from "react";

import { api, errorMessage } from "../api";
import { useAuth } from "../auth";
import { Alert, Card, ErrorBox, Field, Icon, Loading, Modal, PageHeader, Tag, useLoad, useToast } from "../components/ui";
import { dt, initials, ROLE_LABEL } from "../format";
import { useProject } from "../project";
import type { ResourcesOverview, Role, User } from "../types";

const ROLES: Role[] = ["ADMINISTRADOR", "JEFE_DE_PROYECTO", "INTEGRANTE"];

const PERMISSIONS: [string, string, string, string][] = [
  ["Gestionar usuarios y roles", "✓", "Consulta", "—"],
  ["Crear y editar proyectos", "✓", "✓", "—"],
  ["Eliminar proyectos", "✓", "—", "—"],
  ["Importar Carta Gantt", "✓", "✓", "—"],
  ["Editar duraciones y precedencias", "✓", "✓", "—"],
  ["Asignar recursos y tarifas", "✓", "✓", "—"],
  ["Registrar avance y fechas reales", "✓", "✓", "Solo tareas propias"],
  ["Verificar criterios de hitos", "✓", "✓", "—"],
  ["Adjuntar evidencias", "✓", "✓", "✓"],
  ["Configurar KPI y umbrales", "✓", "✓", "—"],
  ["Crear solicitudes de cambio", "✓", "✓", "✓"],
  ["Avanzar, aprobar y aplicar cambios", "✓", "✓", "—"],
  ["Ver Gantt, recursos, KPI y tableros", "✓", "✓", "✓"],
];

export default function UsersPage() {
  const { isManager, isAdmin, user } = useAuth();
  const { projectId, project } = useProject();
  const users = useLoad(() => (isManager ? api.get<User[]>("/users") : Promise.resolve(user ? [user] : [])), [isManager]);
  const resources = useLoad(() => (projectId ? api.get<ResourcesOverview>(`/projects/${projectId}/resources/overview`) : Promise.resolve(null)), [projectId]);
  const [editing, setEditing] = useState<User | "new" | null>(null);

  if (users.loading && !users.data) return <Loading />;
  if (users.error) return <ErrorBox error={users.error} onRetry={() => void users.reload()} />;
  const linked = (id: string) => resources.data?.resources.filter((resource) => resource.user_id === id).map((resource) => `${resource.external_id} · ${resource.name}`) ?? [];

  return (
    <>
      <PageHeader crumb="Sistema" title="Usuarios y roles">
        {isAdmin && (
          <button className="btn pri" onClick={() => setEditing("new")}>
            <Icon name="plus" size={14} /> Nuevo usuario
          </button>
        )}
      </PageHeader>
      <div className="grid" style={{ gridTemplateColumns: "minmax(0,1.3fr) minmax(0,1fr)" }}>
        <Card title={isManager ? `Usuarios (${users.data?.length ?? 0})` : "Mi cuenta"} bodyClass="card-b scroll">
          <table className="t">
            <thead>
              <tr>
                <th>Usuario</th>
                <th>Rol</th>
                <th>Recurso vinculado {project ? `(${project.name})` : ""}</th>
                <th>Estado</th>
                {isAdmin && <th />}
              </tr>
            </thead>
            <tbody>
              {(users.data ?? []).map((item) => (
                <tr key={item.id}>
                  <td>
                    <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                      <span className="avatar">{initials(item.full_name)}</span>
                      <div>
                        <b style={{ fontWeight: 500 }}>{item.full_name}</b>
                        <div className="sub muted">{item.email}</div>
                      </div>
                    </div>
                  </td>
                  <td>
                    {item.roles.map((role) => (
                      <Tag key={role} cls={role === "ADMINISTRADOR" ? "t-acc" : role === "JEFE_DE_PROYECTO" ? "t-info" : "t-mute"}>
                        {ROLE_LABEL[role]}
                      </Tag>
                    ))}
                  </td>
                  <td style={{ fontSize: 12.5 }}>{linked(item.id).join(", ") || <span className="muted">—</span>}</td>
                  <td>
                    <Tag cls={item.is_active ? "t-ok" : "t-mute"}>{item.is_active ? "Activo" : "Inactivo"}</Tag>
                    {item.created_at && <div className="sub muted">desde {dt(item.created_at).slice(0, 10)}</div>}
                  </td>
                  {isAdmin && (
                    <td>
                      <button className="btn sm" onClick={() => setEditing(item)}>
                        <Icon name="edit" size={12} /> Editar
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          {!isAdmin && <p className="muted" style={{ fontSize: 12, marginBottom: 0 }}>Solo el Administrador crea usuarios y asigna roles. El vínculo usuario ↔ profesional se define en Recursos.</p>}
        </Card>
        <Card title="Matriz de permisos por rol">
          <table className="t perm">
            <thead>
              <tr>
                <th>Permiso</th>
                <th className="c">Administrador</th>
                <th className="c">Jefe de Proyecto</th>
                <th className="c">Integrante</th>
              </tr>
            </thead>
            <tbody>
              {PERMISSIONS.map(([label, ...values]) => (
                <tr key={label}>
                  <td>{label}</td>
                  {values.map((value, index) => (
                    <td key={index} className={`c ${value === "✓" ? "yes" : value === "—" ? "no" : ""}`} style={{ fontSize: value.length > 2 ? 11.5 : undefined }}>
                      {value}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted" style={{ fontSize: 12, marginBottom: 0 }}>
            La interfaz oculta las acciones no permitidas y la API las rechaza con 403 aunque se intenten por otro medio.
          </p>
        </Card>
      </div>
      {editing && <UserModal user={editing === "new" ? undefined : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); void users.reload(); }} />}
    </>
  );
}

function UserModal({ user, onClose, onSaved }: { user?: User; onClose: () => void; onSaved: () => void }) {
  const toast = useToast();
  const [email, setEmail] = useState(user?.email ?? "");
  const [name, setName] = useState(user?.full_name ?? "");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>(user?.roles[0] ?? "INTEGRANTE");
  const [active, setActive] = useState(user?.is_active ?? true);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    try {
      if (user) {
        const payload: Record<string, unknown> = { full_name: name, roles: [role], is_active: active };
        if (password) payload.password = password;
        await api.patch(`/users/${user.id}`, payload);
      } else {
        await api.post("/users", { email, full_name: name, password, roles: [role] });
      }
      toast("ok", user ? "Usuario actualizado." : `Usuario ${email} creado.`);
      onSaved();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <Modal
      title={user ? `Editar ${user.full_name}` : "Nuevo usuario"}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            Cancelar
          </button>
          <button className="btn pri" disabled={!name || (!user && (!email || password.length < 8))} onClick={() => void save()}>
            Guardar
          </button>
        </>
      }
    >
      <Field label="Correo">
        <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} disabled={Boolean(user)} />
      </Field>
      <Field label="Nombre completo">
        <input value={name} onChange={(event) => setName(event.target.value)} />
      </Field>
      <Field label={user ? "Nueva contraseña (opcional)" : "Contraseña"} hint="Mínimo 8 caracteres.">
        <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" />
      </Field>
      <Field label="Rol">
        <select value={role} onChange={(event) => setRole(event.target.value as Role)}>
          {ROLES.map((value) => (
            <option key={value} value={value}>
              {ROLE_LABEL[value]}
            </option>
          ))}
        </select>
      </Field>
      {user && (
        <label className="chk">
          <input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} /> Usuario activo
        </label>
      )}
      {error && <Alert level="crit">{error}</Alert>}
    </Modal>
  );
}
