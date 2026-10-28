import { useEffect, useState, type ReactNode } from "react";

import { AuthProvider, useAuth } from "./auth";
import { ErrorBox, Icon, Loading, ToastProvider } from "./components/ui";
import { d, initials, PROJECT_STATUS_LABEL, ROLE_LABEL, statusTag } from "./format";
import { ProjectProvider, useProject } from "./project";
import { go, href, useRoute } from "./router";
import ActivitiesPage from "./pages/Activities";
import ChangeDashboardPage from "./pages/ChangeDashboard";
import ChangeDetailPage from "./pages/ChangeDetail";
import ChangesPage from "./pages/Changes";
import ChecklistPage from "./pages/Checklist";
import GanttPage from "./pages/Gantt";
import ImportPage from "./pages/Import";
import KpiPage from "./pages/Kpis";
import LoginPage from "./pages/Login";
import MilestonesPage from "./pages/Milestones";
import ProjectDashboardPage from "./pages/ProjectDashboard";
import ProjectsPage from "./pages/Projects";
import ResourcesPage from "./pages/Resources";
import UsersPage from "./pages/Users";

type NavItem = { page: string; label: string; group: string; managerOnly?: boolean; needsProject?: boolean };

const NAV: NavItem[] = [
  { page: "proyectos", label: "Proyectos", group: "General" },
  { page: "importar", label: "Importar Carta Gantt", group: "Planificación", managerOnly: true },
  { page: "actividades", label: "Actividades y precedencias", group: "Planificación", needsProject: true },
  { page: "gantt", label: "Carta Gantt", group: "Planificación", needsProject: true },
  { page: "recursos", label: "Recursos y costos", group: "Planificación", needsProject: true },
  { page: "hitos", label: "Hitos", group: "Planificación", needsProject: true },
  { page: "kpi", label: "Administrador de KPI", group: "Control", needsProject: true },
  { page: "cambios", label: "Solicitudes de cambio", group: "Control", needsProject: true },
  { page: "tablero", label: "Tablero del proyecto", group: "Tableros", needsProject: true },
  { page: "tablero-cambio", label: "Tablero del cambio", group: "Tableros", needsProject: true },
  { page: "usuarios", label: "Usuarios y roles", group: "Sistema" },
  { page: "caso", label: "Caso de prueba", group: "Sistema", needsProject: true },
];

export default function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <Gate />
      </AuthProvider>
    </ToastProvider>
  );
}

function Gate() {
  const { user, ready } = useAuth();
  if (!ready) return <Loading text="Iniciando Trazo…" />;
  if (!user) return <LoginPage />;
  return (
    <ProjectProvider>
      <Shell />
    </ProjectProvider>
  );
}

function BrandMark() {
  return (
    <div className="brand-mark">
      <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
        <path d="M2 4h10M2 9h14M2 14h7" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" />
      </svg>
    </div>
  );
}

function Shell() {
  const route = useRoute();
  const { user, logout, isManager, primaryRole } = useAuth();
  const { projects, project, select, loading, error, refresh } = useProject();
  const [menuOpen, setMenuOpen] = useState(false);
  const routeKey = `${route.page}/${route.param ?? ""}`;
  const [lastRoute, setLastRoute] = useState(routeKey);
  if (lastRoute !== routeKey) {
    setLastRoute(routeKey);
    setMenuOpen(false);
  }

  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [routeKey]);

  const items = NAV.filter((item) => !item.managerOnly || isManager);
  const groups = Array.from(new Set(items.map((item) => item.group)));
  const active = route.page === "cambio" ? "cambios" : route.page;

  let page: ReactNode;
  const navItem = NAV.find((item) => item.page === route.page);
  if (loading) page = <Loading />;
  else if (error) page = <ErrorBox error={error} onRetry={() => void refresh()} />;
  else if ((navItem?.needsProject || route.page === "cambio") && !project)
    page = (
      <div className="card card-b empty">
        No hay un proyecto seleccionado. {isManager ? <a href={href("importar")}>Importa una Carta Gantt</a> : "Pide al Jefe de Proyecto que importe uno."}
      </div>
    );
  else page = renderPage(route.page, route.param);

  return (
    <div className="app">
      <aside className="side">
        <div className="brand">
          <BrandMark />
          <div>
            <b>Trazo</b>
            <small>Planificación y control</small>
          </div>
        </div>
        <nav className="nav" aria-label="Secciones">
          {groups.map((group) => (
            <div key={group}>
              <div className="nav-group">{group}</div>
              {items
                .filter((item) => item.group === group)
                .map((item) => (
                  <a key={item.page} href={href(item.page)} className={active === item.page ? "on" : ""}>
                    <span className="n">{String(NAV.indexOf(item) + 1).padStart(2, "0")}</span>
                    {item.label}
                  </a>
                ))}
            </div>
          ))}
        </nav>
        <div className="side-foot">
          <span>{ROLE_LABEL[primaryRole ?? "INTEGRANTE"]}</span>
          <a href="/docs" target="_blank" rel="noreferrer">
            API
          </a>
        </div>
      </aside>
      <div className="main">
        <header className="top">
          <label className="proj-sel">
            <span className="muted" style={{ fontSize: 12 }}>
              Proyecto
            </span>
            <select value={project?.id ?? ""} onChange={(event) => select(event.target.value)} aria-label="Proyecto activo">
              {!projects.length && <option value="">Sin proyectos</option>}
              {projects.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
            {project && <span className={`tag ${statusTag(project.status)}`}>{PROJECT_STATUS_LABEL[project.status]}</span>}
          </label>
          {project && (
            <>
              <span className="cut">
                Fecha de corte <b>{d(project.cutoff_date)}</b>
              </span>
              <span className="cut">
                Línea base <b>{project.baseline_version ?? "—"}</b>
              </span>
            </>
          )}
          <div className="sp" />
          <div className="user-menu">
            <button className="user-btn" onClick={() => setMenuOpen((open) => !open)} aria-expanded={menuOpen}>
              <span className="who">
                <b>{user?.full_name}</b>
                <small>{ROLE_LABEL[primaryRole ?? "INTEGRANTE"]}</small>
              </span>
              <span className="avatar">{initials(user?.full_name)}</span>
            </button>
            {menuOpen && (
              <div className="menu card">
                <div className="muted" style={{ fontSize: 12, padding: "4px 8px 8px" }}>
                  {user?.email}
                </div>
                <button
                  className="btn sm"
                  onClick={() => {
                    logout();
                    go("proyectos");
                  }}
                >
                  <Icon name="logout" size={14} /> Cerrar sesión
                </button>
              </div>
            )}
          </div>
        </header>
        <main className="content">{page}</main>
      </div>
    </div>
  );
}

function renderPage(page: string, param: string | null): ReactNode {
  switch (page) {
    case "proyectos":
      return <ProjectsPage />;
    case "importar":
      return <ImportPage />;
    case "actividades":
      return <ActivitiesPage focus={param} />;
    case "gantt":
      return <GanttPage focus={param} />;
    case "recursos":
      return <ResourcesPage focus={param} />;
    case "hitos":
      return <MilestonesPage focus={param} />;
    case "kpi":
      return <KpiPage focus={param} />;
    case "cambios":
      return <ChangesPage />;
    case "cambio":
      return param ? <ChangeDetailPage id={param} /> : <ChangesPage />;
    case "tablero":
      return <ProjectDashboardPage />;
    case "tablero-cambio":
      return <ChangeDashboardPage />;
    case "usuarios":
      return <UsersPage />;
    case "caso":
      return <ChecklistPage />;
    default:
      return (
        <div className="card card-b empty">
          Página no encontrada. <a href={href("proyectos")}>Volver a proyectos</a>
        </div>
      );
  }
}
