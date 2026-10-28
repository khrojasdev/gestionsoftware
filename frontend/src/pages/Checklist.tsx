import { api } from "../api";
import { useAuth } from "../auth";
import { Card, ErrorBox, Loading, PageHeader, useLoad } from "../components/ui";
import { RESOURCE_TYPE_LABEL } from "../format";
import { useProject } from "../project";
import { href } from "../router";
import type { Checklist } from "../types";

const SCENARIOS = [
  {
    title: "Escenario 1 · Cambiar una duración",
    steps: [
      <>
        Abrir <a href={href("actividades", "A17")}>A17 en Actividades</a> (integración con el sistema de compras, ruta crítica).
      </>,
      <>Cambiar la duración de 22 a 27 días hábiles y presionar «Guardar y recalcular».</>,
      <>El sistema muestra el antes / después: A17, sus sucesoras (A18, A19, H05…) y el término del proyecto se desplazan.</>,
    ],
    see: [
      ["Carta Gantt", "gantt"],
      ["Tablero del proyecto (SPI, reserva)", "tablero"],
      ["KPI", "kpi"],
    ],
  },
  {
    title: "Escenario 2 · Modificar recursos",
    steps: [
      <>
        Abrir <a href={href("recursos", "A18")}>Recursos → Por tarea</a> y hacer clic en la asignación de IN1 en A18.
      </>,
      <>Subir las horas por día de 8 a 16 y marcar «Duración guiada por esfuerzo».</>,
      <>La duración de A18 se reduce a la mitad, el plan se adelanta y aparece la alerta de sobreasignación de IN1 (200 %).</>,
    ],
    see: [
      ["Alertas de sobreasignación y carga semanal", "recursos"],
      ["Carta Gantt", "gantt"],
      ["Costos por etapa", "recursos"],
    ],
  },
  {
    title: "Escenario 3 · Aprobar una solicitud de cambio",
    steps: [
      <>
        Abrir <a href={href("cambios")}>SC-04</a> (exportación PDF del tablero ejecutivo), que está en «Revisión del comité» con su impacto simulado: +4 días hábiles y +$736.000.
      </>,
      <>Avanzar a «Decisión», aprobar y presionar «Aplicar cambio al plan y generar nueva línea base».</>,
      <>Se congela la línea base siguiente, el Gantt y los costos se recalculan y los KPI C01–C12 cambian.</>,
    ],
    see: [
      ["Tablero del cambio", "tablero-cambio"],
      ["Carta Gantt (nueva línea base)", "gantt"],
      ["KPI de cambio", "kpi"],
    ],
  },
];

export default function ChecklistPage() {
  const { projectId, version, project } = useProject();
  const { isManager } = useAuth();
  const { data, error, loading, reload } = useLoad(() => api.get<Checklist>(`/projects/${projectId}/checklist`), [projectId, version]);
  if (loading && !data) return <Loading />;
  if (error || !data) return <ErrorBox error={error ?? "Sin datos"} onRetry={() => void reload()} />;
  const passed = data.items.filter((item) => item.ok).length;
  return (
    <>
      <PageHeader crumb="Sistema · Demostración" title="Verificación del caso de prueba" />
      <div className="grid" style={{ gridTemplateColumns: "minmax(0,1fr) minmax(0,1.6fr)", alignItems: "start" }}>
        <Card title={`Evidencia mínima · ${data.project}`} actions={<span className={`tag ${passed === data.items.length ? "t-ok" : "t-warn"}`}>{passed}/{data.items.length}</span>}>
          {data.items.map((item) => (
            <div className="check" key={item.label}>
              <span className={`ci ${item.ok ? "y" : "w"}`}>{item.ok ? "✓" : "!"}</span>
              <span>{item.label}</span>
              <span className="cnt">
                {item.value}
                {item.required !== null && item.required !== undefined ? ` / mín. ${item.required}` : ""}
              </span>
            </div>
          ))}
          <p className="muted" style={{ fontSize: 12, marginBottom: 0 }}>
            Tipos de precedencia: <span className="mono">{data.dependency_types.join(", ")}</span>
            <br />
            Tipos de recurso: {data.resource_types.map((type) => RESOURCE_TYPE_LABEL[type] ?? type).join(", ")}
          </p>
        </Card>
        <div className="grid">
          {project?.code !== "HORIZONTE-CONECTA" && (
            <div className="alert info">
              <div>Los escenarios están preparados sobre el proyecto Horizonte Conecta. Selecciónalo arriba para seguirlos tal cual.</div>
            </div>
          )}
          {!isManager && (
            <div className="alert warn">
              <div>Los tres escenarios requieren el rol Jefe de Proyecto o Administrador (kevin.henriquez@trazo.cl).</div>
            </div>
          )}
          <div className="flow">
            {SCENARIOS.map((scenario) => (
              <div className="fi" key={scenario.title}>
                <h4>{scenario.title}</h4>
                <ol>
                  {scenario.steps.map((step, index) => (
                    <li key={index}>{step}</li>
                  ))}
                </ol>
                <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
                  Ver en:{" "}
                  {scenario.see.map(([label, page], index) => (
                    <span key={label}>
                      {index ? " · " : ""}
                      <a href={href(page)}>{label}</a>
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <Card title="Para repetir la demostración">
            <p style={{ margin: 0, fontSize: 13 }}>
              Los escenarios modifican el plan. Para volver al estado inicial ejecuta <span className="mono">python -m app.demo --reset</span> en el backend (o el script <span className="mono">reiniciar-demo</span> descrito en el README), que recrea los dos proyectos con sus avances, solicitudes y KPI.
            </p>
          </Card>
        </div>
      </div>
    </>
  );
}
