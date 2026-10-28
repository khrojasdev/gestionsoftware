import { useRef, useState, type DragEvent } from "react";

import { api, errorMessage, templateUrl } from "../api";
import { useAuth } from "../auth";
import { Alert, Card, Field, Icon, Loading, PageHeader, ReadOnlyNote, Tag, useToast } from "../components/ui";
import { d, fileSize, money } from "../format";
import { useProject } from "../project";
import { go } from "../router";
import type { ImportPreview, ProjectOverview } from "../types";

const STRUCTURE: { sheet: string; text: string }[] = [
  { sheet: "Proyecto", text: "clave / valor: código, nombre, cliente, fechas, presupuesto, contingencia, fecha de corte." },
  { sheet: "Gantt", text: "id, tipo (ETAPA/ACTIVIDAD/SUBACTIVIDAD/HITO), nombre, padre_id, duración, predecesoras (A02;A40FF+2), avance y fechas reales." },
  { sheet: "Recursos", text: "recurso_id, nombre, tipo (HUMANO, EQUIPAMIENTO, INFRAESTRUCTURA_LICENCIA, SERVICIO_EXTERNO), rol, tarifa, capacidad h/día." },
  { sheet: "Asignaciones", text: "tarea_id, recurso_id, horas planificadas o cantidad, h/día y tarifa especial." },
  { sheet: "Calendario", text: "Feriados y días no laborables por proyecto o recurso." },
  { sheet: "Criterios · Hitos_Tareas", text: "Criterios de aceptación por hito y tareas que lo componen." },
  { sheet: "KPI_Proyecto_Hitos · KPI_Cambio", text: "Catálogo de KPI con fórmula, umbrales y unidad (opcional)." },
  { sheet: "Etapas_Cambio · Cambios", text: "Flujo de 10 etapas con SLA y solicitudes existentes (opcional)." },
];

export default function ImportPage() {
  const { isManager } = useAuth();
  const { projects, select, touch } = useProject();
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [busy, setBusy] = useState<"preview" | "import" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const [mode, setMode] = useState<"nuevo" | "reemplazar">("nuevo");
  const [code, setCode] = useState("");
  const [name, setName] = useState("");

  async function inspect(selected: File) {
    setFile(selected);
    setPreview(null);
    setError(null);
    setBusy("preview");
    try {
      const result = await api.upload<ImportPreview>("/projects/import/preview", selected);
      const taken = projects.some((project) => project.code === result.project_code);
      const used = new Set(projects.map((project) => project.code));
      let suggestion = result.project_code;
      for (let index = 2; taken && used.has(suggestion); index += 1) suggestion = `${result.project_code}-${index}`;
      setCode(suggestion);
      setName(taken ? `${result.project.nombre ?? result.project_code} (${suggestion.split("-").pop()})` : result.project.nombre ?? "");
      setMode("nuevo");
      setPreview(result);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  const existing: ProjectOverview | undefined = preview ? projects.find((project) => project.code === preview.project_code) : undefined;

  async function confirm() {
    if (!file || !preview) return;
    setBusy("import");
    setError(null);
    try {
      if (existing && mode === "reemplazar") {
        await api.upload(`/projects/${existing.id}/imports`, file);
        select(existing.id);
        toast("ok", `Planificación de ${existing.name} reemplazada desde ${file.name}. Se generó una nueva línea base.`);
      } else {
        const result = await api.upload<{ project: ProjectOverview }>("/projects/import", file, { codigo: code.trim(), nombre: name.trim() });
        select(result.project.id);
        toast("ok", `Proyecto ${result.project.name} importado con línea base v1.`);
      }
      touch();
      go("gantt");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDrag(false);
    const dropped = event.dataTransfer.files?.[0];
    if (dropped) void inspect(dropped);
  }

  if (!isManager)
    return (
      <>
        <PageHeader crumb="Planificación" title="Importar Carta Gantt" />
        <ReadOnlyNote>Solo el Administrador o el Jefe de Proyecto pueden importar planificaciones.</ReadOnlyNote>
      </>
    );

  const info = preview?.project ?? {};
  return (
    <>
      <PageHeader crumb="Planificación" title="Importar Carta Gantt">
        <a className="btn" href={templateUrl()} download>
          <Icon name="download" size={14} /> Descargar plantilla .xlsx
        </a>
      </PageHeader>
      <div className="split">
        <div className="grid">
          <Card title="1 · Selecciona el archivo">
            <div
              className={`drop ${drag ? "drag" : ""}`}
              onDragOver={(event) => {
                event.preventDefault();
                setDrag(true);
              }}
              onDragLeave={() => setDrag(false)}
              onDrop={onDrop}
            >
              <Icon name="upload" size={22} />
              <p style={{ margin: "8px 0 4px" }}>
                Arrastra aquí la Carta Gantt (<b>.xlsx</b>, <b>.csv</b> o <b>.json</b>)
              </p>
              <p className="muted" style={{ margin: "0 0 12px", fontSize: 12.5 }}>
                Se acepta la plantilla de Trazo o el libro de planificación del curso (hojas Cronograma / Planificación / Calendario), que se convierte automáticamente.
              </p>
              <button className="btn dark" onClick={() => input.current?.click()}>
                Elegir archivo
              </button>
              <input
                ref={input}
                type="file"
                accept=".xlsx,.csv,.json"
                hidden
                onChange={(event) => {
                  const selected = event.target.files?.[0];
                  if (selected) void inspect(selected);
                  event.target.value = "";
                }}
              />
            </div>
            {file && (
              <div className="file" style={{ marginTop: 12 }}>
                <div className="xls">{file.name.split(".").pop()?.toUpperCase()}</div>
                <div style={{ flex: 1 }}>
                  <b>{file.name}</b>
                  <div className="muted" style={{ fontSize: 12 }}>
                    {fileSize(file.size)}
                    {preview && ` · ${preview.inspection.label}`}
                  </div>
                </div>
                {preview && <Tag cls={preview.valid ? "t-ok" : "t-crit"}>{preview.valid ? "Válido" : "Con errores"}</Tag>}
              </div>
            )}
            {busy === "preview" && <Loading text="Validando estructura, fechas, precedencias y recursos…" />}
            {error && (
              <div style={{ marginTop: 12 }}>
                <Alert level="crit">{error}</Alert>
              </div>
            )}
          </Card>

          {preview && (
            <>
              <Card title="2 · Revisión del archivo" actions={<Tag cls="t-info">{preview.inspection.format === "HORIZONTE" ? "Convertido desde libro del curso" : "Plantilla Trazo"}</Tag>}>
                <div className="grid g4" style={{ marginBottom: 14 }}>
                  {(["ETAPA", "ACTIVIDAD", "SUBACTIVIDAD", "HITO"] as const).map((kind) => (
                    <div key={kind} className="mini-stat">
                      <b>{preview.summary.elements[kind] ?? 0}</b>
                      <span>{{ ETAPA: "Etapas", ACTIVIDAD: "Actividades", SUBACTIVIDAD: "Subactividades", HITO: "Hitos" }[kind]}</span>
                    </div>
                  ))}
                  <div className="mini-stat">
                    <b>{preview.summary.resources_human}</b>
                    <span>Profesionales</span>
                  </div>
                  <div className="mini-stat">
                    <b>{preview.summary.resources_other}</b>
                    <span>Recursos no humanos</span>
                  </div>
                  <div className="mini-stat">
                    <b>{preview.summary.assignments}</b>
                    <span>Asignaciones</span>
                  </div>
                  <div className="mini-stat">
                    <b>{preview.summary.criteria}</b>
                    <span>Criterios de aceptación</span>
                  </div>
                </div>
                <table className="t">
                  <thead>
                    <tr>
                      <th>Hoja</th>
                      <th className="num">Filas</th>
                      <th>Columnas</th>
                      <th>Estado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.inspection.sheets.map((sheet) => (
                      <tr key={sheet.name}>
                        <td className="mono">{sheet.name}</td>
                        <td className="num mono">{sheet.rows}</td>
                        <td style={{ whiteSpace: "normal", fontSize: 12 }} className="muted">
                          {sheet.found.join(", ") || "—"}
                        </td>
                        <td>{sheet.missing.length ? <Tag cls="t-crit">Faltan {sheet.missing.join(", ")}</Tag> : <Tag cls="t-ok">{sheet.converted ? "Convertida" : "Completa"}</Tag>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>

              <Card title={`3 · Validación (${preview.report.errors.length} errores, ${preview.report.warnings.length} advertencias)`}>
                {!preview.report.errors.length && !preview.report.warnings.length && <Alert level="ok">Sin observaciones: jerarquía, fechas, precedencias, recursos y costos consistentes.</Alert>}
                <div className="grid" style={{ gap: 8 }}>
                  {preview.report.errors.map((issue, index) => (
                    <Alert key={`e${index}`} level="crit">
                      <b>{issue.sheet ?? "Archivo"}{issue.row ? ` fila ${issue.row}` : ""}{issue.column ? ` · ${issue.column}` : ""}:</b> {issue.message}
                    </Alert>
                  ))}
                  {preview.report.warnings.map((issue, index) => (
                    <Alert key={`w${index}`} level="warn">
                      <b>{issue.sheet ?? "Archivo"}{issue.row ? ` fila ${issue.row}` : ""}:</b> {issue.message}
                    </Alert>
                  ))}
                </div>
              </Card>

              <Card title="Vista previa de las primeras filas del Gantt" bodyClass="card-b scroll">
                <table className="t">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Tipo</th>
                      <th>Nombre</th>
                      <th>Padre</th>
                      <th className="num">Duración</th>
                      <th>Predecesoras</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.sample.map((row, index) => (
                      <tr key={index}>
                        <td className="mono">{String(row.id ?? "")}</td>
                        <td>{String(row.tipo ?? "")}</td>
                        <td className="ell" style={{ maxWidth: 320 }}>
                          {String(row.nombre ?? "")}
                        </td>
                        <td className="mono">{String(row.padre_id ?? "")}</td>
                        <td className="num mono">{String(row.duracion_dias ?? "")}</td>
                        <td className="mono">{String(row.predecesoras ?? "")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            </>
          )}
        </div>

        <div className="drawer grid">
          {preview ? (
            <Card title="4 · Confirmar importación">
              <dl className="kv">
                <dt>Código</dt>
                <dd className="mono">{preview.project_code}</dd>
                <dt>Nombre</dt>
                <dd>{info.nombre ?? "—"}</dd>
                <dt>Cliente</dt>
                <dd>{info.cliente ?? "—"}</dd>
                <dt>Inicio</dt>
                <dd className="mono">{d(info.fecha_inicio)}</dd>
                <dt>Compromiso</dt>
                <dd className="mono">{d(info.fecha_comprometida)}</dd>
                <dt>Presupuesto</dt>
                <dd className="mono">{info.presupuesto ? money(Number(info.presupuesto)) : "—"}</dd>
                <dt>Fecha de corte</dt>
                <dd className="mono">{d(info.fecha_corte)}</dd>
                <dt>Feriados</dt>
                <dd>{preview.summary.holidays}</dd>
                <dt>KPI</dt>
                <dd>{preview.summary.kpis}</dd>
              </dl>
              {existing && (
                <div style={{ marginTop: 12 }}>
                  <Alert level="warn">
                    El archivo trae el código de <b>{existing.name}</b>, que ya existe. Elige qué hacer:
                  </Alert>
                  <label className={`rolecard ${mode === "nuevo" ? "on" : ""}`} style={{ marginTop: 8 }}>
                    <input type="radio" name="mode" checked={mode === "nuevo"} onChange={() => setMode("nuevo")} />
                    <div>
                      <b>Crear como proyecto nuevo</b>
                      <br />
                      <span className="muted">El proyecto actual no se toca; se crea otro con el código y nombre de abajo.</span>
                    </div>
                  </label>
                  <label className={`rolecard ${mode === "reemplazar" ? "on" : ""}`}>
                    <input type="radio" name="mode" checked={mode === "reemplazar"} onChange={() => setMode("reemplazar")} />
                    <div>
                      <b>Reemplazar la planificación de {existing.name}</b>
                      <br />
                      <span className="muted">Sobrescribe Gantt, recursos y asignaciones y genera una nueva línea base.</span>
                    </div>
                  </label>
                </div>
              )}
              {(!existing || mode === "nuevo") && (
                <div style={{ marginTop: 12 }}>
                  <Field label="Código del proyecto">
                    <input className="mono" value={code} onChange={(event) => setCode(event.target.value.toUpperCase())} />
                  </Field>
                  <Field label="Nombre del proyecto">
                    <input value={name} onChange={(event) => setName(event.target.value)} />
                  </Field>
                  {projects.some((project) => project.code === code.trim()) && <Alert level="crit">Ya existe un proyecto con ese código; usa otro.</Alert>}
                </div>
              )}
              <button
                className="btn pri"
                style={{ width: "100%", justifyContent: "center", marginTop: 14 }}
                disabled={!preview.valid || busy !== null || ((!existing || mode === "nuevo") && (!code.trim() || projects.some((project) => project.code === code.trim())))}
                onClick={() => void confirm()}
              >
                {busy === "import" ? "Importando y calculando…" : existing && mode === "reemplazar" ? "Reemplazar planificación" : "Crear proyecto y calcular"}
              </button>
              {!preview.valid && <p className="muted" style={{ fontSize: 12 }}>Corrige los errores en el archivo y vuelve a cargarlo.</p>}
            </Card>
          ) : (
            <Card title="Estructura esperada">
              <p className="muted" style={{ marginTop: 0, fontSize: 12.5 }}>
                La plantilla tiene una hoja por entidad. La jerarquía (Etapa → Actividad → Subactividad / Hito) vive dentro del Gantt mediante <span className="mono">padre_id</span>.
              </p>
              <Alert level="info">
                Antes de confirmar puedes cambiar el código y el nombre del proyecto. Si el código del archivo ya existe, eliges entre <b>crear un proyecto nuevo</b> o <b>reemplazar</b> el existente. Si el archivo no trae KPI ni etapas de cambio, se crean los 20 KPI y el flujo de 10 etapas estándar.
              </Alert>
              {STRUCTURE.map((item) => (
                <div key={item.sheet} className="check">
                  <span className="ci y">
                    <Icon name="file" size={12} />
                  </span>
                  <div>
                    <b className="mono" style={{ fontSize: 12 }}>
                      {item.sheet}
                    </b>
                    <div className="muted" style={{ fontSize: 12 }}>
                      {item.text}
                    </div>
                  </div>
                </div>
              ))}
            </Card>
          )}
          <Card title="Qué hace el sistema al importar">
            <ol style={{ margin: 0, paddingLeft: 18, fontSize: 12.5, color: "var(--ink-2)" }}>
              <li>Valida hojas, columnas, jerarquía, duraciones y referencias.</li>
              <li>Detecta ciclos y precedencias inválidas (FS, SS, FF, SF con desfase).</li>
              <li>Calcula fechas con calendario laboral y feriados, ruta crítica y holguras.</li>
              <li>Calcula costos por recurso, tarea, etapa y proyecto.</li>
              <li>Congela la línea base y calcula KPI a la fecha de corte.</li>
            </ol>
          </Card>
        </div>
      </div>
    </>
  );
}
