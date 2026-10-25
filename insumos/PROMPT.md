# PROYECTO: "Trazo" — Plataforma de planificación y control de proyectos desde una Carta Gantt

## 0. Cómo debes trabajar (instrucciones para Lemoria)
- Usa el flujo SDD completo de Lemoria: Discovery → Spec → PRD → Tasks → Architecture → Implementation → Testing → Review → Commit → Push → Documentation → Memory Update → State Machine.
- El orchestrator coordina y delega así:
  - db-agent: modelo de datos, migraciones e integridad referencial.
  - implementation-agent: motor de cálculo, importador, API y reglas de negocio.
  - frontend-agent: UI basada en los mockups.
  - testing-agent: pytest unitario y de integración. El motor de cálculo debe tener cobertura ≥ 90 %.
  - review-agent: revisión de código y arquitectura.
  - documentation-agent: README, documentación técnica, manual de usuario y vault.
  - github-agent: Conventional Commits con el trailer "Task: <uuid>".
- Discovery: lee TODO lo que hay en insumos/ antes de especificar:
  - Rubrica_Proyecto_Integrador_2.pdf: la rúbrica, que manda.
  - Caso3_Horizonte_Planificacion_Gantt.xlsx: datos reales del proyecto Horizonte Conecta.
  - Trazo_Mockups.html: 15 pantallas de referencia visual y funcional.
  - Caso3_Horizonte_Documento_Trabajo_v2.pdf y Caso3_Horizonte_Project_Charter.pdf: contexto, recursos, tarifas, riesgos.
  - Caso3_Horizonte_EDT_Diccionario.pdf (si existe): solo como referencia de nombres de etapas y actividades.
- Cada tarea del backlog debe indicar qué indicador de la rúbrica cubre (Ind. 1 a 8) y su criterio de aceptación verificable.
- Registra un ADR para cada decisión relevante: stack, motor de programación, parser de fórmulas, formato de importación e integración de IA.
- Prioriza según el peso de la rúbrica. El Ind. 8 "Integración, pruebas y demostración" vale 50 %, así que construye primero un corte vertical funcional de punta a punta (importar → Gantt → recursos/costos → KPI → cambio aprobado → tableros) y después profundiza cada módulo.
- No me preguntes lo que puedas decidir con buenas prácticas. Pregúntame SOLO lo que está en la sección 14 (preguntas abiertas).
- IMPORTANTE: Lemoria usa PostgreSQL para su propia memoria. La base de datos de la aplicación debe ser OTRA base, separada: nombre "trazo_db", usuario propio y, de preferencia, un contenedor Docker propio en otro puerto (p. ej. 5433). Nunca mezcles tablas de la app con las de Lemoria.
- Entorno: Windows 11. La terminal es CMD/PowerShell; los scripts del proyecto deben funcionar en Windows (preferir scripts Python o .ps1/.bat en vez de bash, o Docker).
- Estructura del proyecto:
  - La raíz es la carpeta "C:\Users\khrva\OneDrive\Desktop\ev2 gestion de software". Todo se crea dentro de ella:
    - backend/
    - frontend/
    - docs/ (documentación técnica, ADRs, vault)
    - scripts/
    - seeds/
    - docker-compose.yml
    - README.md
  - insumos/ es SOLO LECTURA: no modifiques, muevas ni renombres sus archivos. Puedes versionarla en git para tener trazabilidad.
  - El nombre de la carpeta raíz tiene espacios. Siempre usa rutas entre comillas.
    - En docker-compose, define "name: trazo".
    - Ningún paquete, módulo ni imagen debe tomar su nombre de la carpeta raíz.
  - La carpeta está dentro de OneDrive: incluye un .gitignore completo (node_modules, .venv, __pycache__, dist, .env, volúmenes de datos) y no guardes datos de PostgreSQL dentro de la carpeta del proyecto (usa volúmenes de Docker con nombre).

## 1. Contexto académico
- Asignatura: Gestión de Proyectos de Software, Duoc UC. Evaluación grupal: "Proyecto integrador: sistema de planificación, seguimiento y gestión del cambio".
- Equipo: Kevin Henríquez Rojas (Jefe de Proyecto), Diego López Fuentes y Christian Pérez Vera.
- Caso de datos: Caso 3, Constructora Horizonte, proyecto "Horizonte Conecta" (05-10-2026 → 12-07-2027, plazo máximo 04-08-2027, costo base $212.809.000, contingencia 10 % de $21.300.000, presupuesto $234.109.000).
- La rúbrica evalúa 8 indicadores:
  1. Requerimientos y modelo de datos (5 %)
  2. Administración de proyectos y estructura jerárquica (5 %)
  3. Recursos, tiempos y costos (10 %)
  4. Carta Gantt y precedencias (10 %)
  5. KPI (10 %)
  6. Gestión del cambio (5 %)
  7. Dos tableros de comando (5 %)
  8. Integración, pruebas y demostración (50 %)
- Evidencia mínima del caso de prueba: 4 etapas, 12 actividades, 20 subactividades, 4 tipos de dependencia (FS, SS, FF, SF), 5 profesionales, 4 tipos de recursos, 6 hitos, 8 KPI de proyecto e hitos, 5 solicitudes de cambio, 12 KPI de gestión del cambio y 2 tableros.
- La demostración debe: (a) cambiar una duración, (b) modificar recursos y (c) aprobar una solicitud de cambio. En los tres casos se deben ver los efectos en Gantt, costos, KPI y tableros.

## 2. Cambio principal respecto de los mockups: SIN módulo EDT
- Elimina las pantallas "Importar EDT" y "EDT / WBS". La unidad de trabajo es la CARTA GANTT.
- El usuario sube un archivo de Carta Gantt (formato de la sección 3) y desde ahí se construye todo.
- La rúbrica igual exige jerarquía etapa → actividad → subactividad, con consolidación. Esa jerarquía vive DENTRO de la Gantt: filas agrupadas y plegables, con totales consolidados en las filas de etapa y actividad. No es un módulo aparte.
- Mantén todas las demás secciones de insumos/Trazo_Mockups.html, ajustadas a este cambio y a las mejoras de la sección 5.
- Los mockups son referencia de layout y contenido, no un diseño cerrado. Respeta: menú lateral por grupos, franja de proyecto con fecha de corte y línea base, selector de rol, tarjetas KPI, tablas y alertas.

## 3. Archivo de entrada: plantilla "Carta Gantt" (.xlsx; también CSV por hoja)
La plataforma debe:
- Ofrecer la plantilla descargable con instrucciones y un ejemplo.
- Validar todo antes de guardar.
- Mostrar vista previa con errores por hoja, fila y columna.
- Importar de forma transaccional: todo o nada.
- Crear la línea base v1.0.

Hojas y columnas (los nombres exactos los define la Spec; esta es la estructura mínima):

### Hoja "Proyecto" (clave | valor)
codigo, nombre, cliente, responsable, fecha_inicio, fecha_comprometida, presupuesto, contingencia_pct, horas_por_dia (8), dias_laborales (L-V), fecha_corte.

### Hoja "Calendario"
fecha | tipo (FERIADO | NO_LABORABLE | EXCEPCION_RECURSO) | recurso_id (opcional) | descripcion

### Hoja "Gantt" (una fila por elemento)
- id: único. Ej.: E1, AC1, A01, H01.
- tipo: ETAPA | ACTIVIDAD | SUBACTIVIDAD | HITO
- nombre
- padre_id: SUBACTIVIDAD → ACTIVIDAD → ETAPA; un HITO cuelga de una actividad o etapa.
- inicio_plan, fin_plan y duracion_dias (días hábiles). Se exigen dos de los tres; el tercero se calcula.
- predecesoras: lista "ID[TIPO][±desfase]" separada por ";". Ej.: "A16; A10SS+2; A05FF-1; A07SF". El tipo por defecto es FS y el desfase va en días hábiles, puede ser negativo.
- avance_pct, inicio_real, fin_real (opcionales, para seguimiento).
- costo_real (opcional, si no se registra por asignación).

Las filas ETAPA y ACTIVIDAD no traen fechas ni costos propios: se consolidan.

### Hoja "Recursos"
- recurso_id
- nombre: para personas, el trabajador. Ej.: "Christian Pérez".
- tipo: HUMANO | EQUIPAMIENTO | INFRAESTRUCTURA_LICENCIA | SERVICIO_EXTERNO
- rol: Ej.: "Desarrollador Frontend/Móvil".
- tarifa: por hora para HUMANO; costo unitario para los demás.
- unidad: hora, mes, unidad, servicio…
- capacidad_h_dia (solo HUMANO)

### Hoja "Asignaciones" (tarea × recurso)
- tarea_id: subactividad.
- recurso_id
- horas_planificadas (HUMANO) o cantidad (no humano)
- h_dia: dedicación diaria en esa tarea.
- tarifa_override (opcional)

Un mismo trabajador puede estar en varias tareas con distintas horas y dedicación. Ej.: Dev Front 8 h/día en A20 y 4 h/día en A21.

### Hoja "Criterios" (criterios de aceptación de hitos)
hito_id | criterio_id | descripcion | forma_de_verificacion | responsable

### Hoja "Hitos_Tareas" (opcional)
hito_id | tarea_id. Vincula explícitamente las tareas y actividades que componen un hito, además de sus predecesoras.

### Validaciones obligatorias
- IDs únicos.
- padre_id existente y con nivel coherente.
- Fechas válidas y fin ≥ inicio.
- Duración coherente con el calendario.
- Predecesoras existentes, tipos válidos y desfase entero.
- Detección de CICLOS: rechazar e informar la cadena exacta. Ej.: "A17 → A18 → A26 → A17".
- Recursos y tareas de asignación existentes; horas > 0.
- Hitos con duración 0 y al menos un criterio.
- Advertencias (no bloqueantes): tareas sin recurso, sobreasignación detectada, solo dependencias FS.

### Conversión del Excel actual
Incluye un conversor (script + opción en el asistente de importación) que transforme insumos/Caso3_Horizonte_Planificacion_Gantt.xlsx a la plantilla:
- Hojas usadas: "Cronograma", "Planificación", "Calendario".
- La columna "Paquete EDT" se usa solo para derivar etapa (1.x) y actividad (1.x.y).
- La subactividad es cada A## y los hitos son los H##.
- Recursos: un trabajador por cada unidad de dotación del rol (p. ej. "Desarrollador Backend 1" y "Desarrollador Backend 2").
- Esfuerzo y horas: hoja "Planificación".
- Tarifas y recursos no laborales: de insumos/Caso3_Horizonte_Documento_Trabajo_v2.pdf, sección 14. Ej.: Jefe de Proyecto $30.000/h, Dev Backend $24.000/h, Dev Integraciones $26.000/h, Analista QA $18.500/h.

El resultado de la conversión se guarda en seeds/, nunca en insumos/.

## 4. Motor de cálculo (núcleo del Ind. 8; todo determinístico en el backend)
- Calendario laboral: horas/día, días hábiles y feriados de Chile, más excepciones por recurso.
- Programación:
  - Pase hacia adelante y hacia atrás en días hábiles.
  - Holgura total y libre.
  - Ruta crítica (holgura total = 0).
  - Las 4 dependencias con desfase:
    - FS: inicio_B ≥ fin_A + 1 + desfase
    - SS: inicio_B ≥ inicio_A + desfase
    - FF: fin_B ≥ fin_A + desfase
    - SF: fin_B ≥ inicio_A + desfase
- Recálculo automático de todas las sucesoras al cambiar una duración, fecha, dependencia o asignación. La respuesta debe incluir la lista de elementos cambiados, con antes y después.
- Fechas proyectadas según el avance real a la fecha de corte:
  - Tarea en curso: fin_proyectado = corte + ceil(duración × (1 − avance)).
- Duración por esfuerzo (opcional por tarea): duración = ceil(horas / Σ h_dia de los asignados).
- Costos:
  - Costo plan de una tarea = Σ horas × tarifa + Σ cantidad × costo_unitario.
  - Costo real: lo registrado.
- Consolidación hacia actividad, etapa y proyecto:
  - Inicio = mínimo de las hijas; fin = máximo.
  - Costos sumados.
  - Avance ponderado por costo planificado (configurable a horas).
- Valor ganado:
  - %plan(t) = días hábiles transcurridos / duración
  - PV = Σ costo × %plan
  - EV = Σ costo × %real
  - AC = Σ costo real
  - Además: SPI, CPI, SV, CV, EAC = BAC/CPI, ETC y VAC.
- Carga por trabajador y día = Σ h_dia de sus asignaciones activas, comparada con su capacidad. Sobreasignación si supera el 100 %.
- Líneas base versionadas e inmutables (v1.0, v1.1…). Toda comparación plan vs real se hace contra la línea base vigente.
- Tests pytest con valores esperados exactos para:
  - cada tipo de dependencia, con desfase positivo y negativo;
  - feriados;
  - ciclos;
  - propagación;
  - consolidación;
  - EVM;
  - sobreasignación.

## 5. Módulos y pantallas (mantener las de los mockups, sin EDT)
1. Inicio de sesión con dos roles.
2. Proyectos: crear, editar, consultar y cerrar. Estado, responsable, presupuesto y avance consolidado. Cerrar exige subactividades al 100 %, cambios cerrados y acta adjunta.
3. Importar Carta Gantt: asistente con los pasos subir → mapear columnas → validar → vista previa → confirmar. Botones para descargar la plantilla y convertir el Excel de Horizonte.
4. Actividades y precedencias:
   - Tabla editable con fechas plan y real, duración, predecesoras (tipo + desfase), holgura, estado y ruta crítica.
   - Panel de edición con alerta de ciclo rechazado y vista previa de las sucesoras que se recalcularán.
5. Carta Gantt (pantalla central):
   - Jerárquica y plegable por etapa y actividad.
   - Barras plan (línea base) vs real/proyectado, porcentaje de avance, hitos como rombos y línea de fecha de corte.
   - Flechas de los 4 tipos de vínculo y ruta crítica resaltada.
   - Zoom semana/mes; filtros (solo críticas, atrasadas, por recurso).
   - Al hacer clic en una barra se abre un panel con detalle, recursos y costos.
   - Edición de duración desde el panel, con recálculo inmediato.
6. Recursos y costos (MEJORADO):
   - Vista por TRABAJADOR/RECURSO: a qué tareas y actividades está asignado, horas por tarea, h/día, periodo, costo por tarea y total; costo plan vs real.
   - Vista por TAREA: qué trabajadores y recursos tiene, con horas, cantidades, tarifas y costo. Se puede agregar o quitar y cambiar horas, con recálculo de duración y costo.
   - Matriz trabajador × tarea con horas planificadas, totales por fila y columna.
   - Carga semanal por trabajador (mapa de calor). Al pinchar una celda se ven las tareas que la componen.
   - Alertas de sobreasignación que indican qué tareas se superponen.
   - Totales por tipo de recurso (4 tipos) y por etapa.
   - Calendario y feriados.
7. Hitos (MEJORADO):
   - Línea de tiempo y tabla: fecha base, fecha real o proyectada, desviación y estado.
   - Cada hito se despliega en dos partes:
     - (a) Tareas y actividades asociadas, con su avance y estado.
     - (b) Desplegable (acordeón) de CRITERIOS DE ACEPTACIÓN: cada criterio con estado (pendiente / cumplido / no cumplido), verificador, fecha y evidencia adjunta.
   - Regla: un hito solo se marca cumplido cuando todos sus criterios están cumplidos.
   - KPI de hitos.
8. Administrador de KPI (MEJORADO):
   - Cada KPI muestra su fórmula, el catálogo de variables (con descripción, fuente y forma de cálculo) y un "desglose" paso a paso del valor actual. Ej.: "CPI = EV / AC = $63.346.433 / $64.764.209 = 0,98".
   - Fórmula EDITABLE con un parser seguro de expresiones: sin eval; solo variables del catálogo, operadores + − × ÷, paréntesis y funciones permitidas (sum, avg, min, max, count, if).
   - También editable: meta, umbrales verde/amarillo/rojo, frecuencia, ámbito (proyecto / etapa / hito) y regla de alerta.
   - Botón "probar fórmula" con vista previa.
   - Versionado de cambios de fórmula (quién, cuándo, antes y después).
   - Histórico por fecha de corte (snapshots).
   - KPI de proyecto e hitos (8): SPI, CPI, SV, CV, desviación de avance físico, % actividades atrasadas, % hitos cumplidos a tiempo, desviación del hito de cierre.
   - KPI de cambio (12):
     - solicitudes registradas
     - tasa de aprobación
     - tasa de rechazo
     - tiempo medio de ciclo
     - tiempo medio de evaluación de impacto
     - impacto acumulado en costo
     - impacto acumulado en plazo
     - % con evidencia completa
     - solicitudes fuera de SLA
     - y 3 ADICIONALES: consumo de contingencia, índice de adopción y cobertura de capacitación (por confirmar, sección 14).
9. Solicitudes de cambio:
   - Registro y filtros: estado, tipo (alcance / plazo / costo / recursos), prioridad, responsable y etapa del flujo.
   - Columnas de impacto en plazo y costo, y cantidad de evidencias.
10. Detalle de solicitud:
    - Flujo de 10 etapas configurable (por defecto): Registro, Revisión inicial, Clasificación y prioridad, Análisis de impacto, Revisión del comité, Decisión, Planificación del cambio, Implementación, Verificación, Cierre y línea base. Cada etapa tiene SLA.
    - Análisis de impacto calculado por SIMULACIÓN (what-if sobre una copia de la programación): Δ fin del proyecto, Δ costo, Δ reserva, actividades afectadas y efecto en recursos.
    - Comparación línea base vigente vs propuesta.
    - Evidencias: subir archivos.
    - Trazabilidad completa: bitácora con usuario y fecha.
    - Aprobar y aplicar → crea línea base vN+1 y recalcula Gantt, costos, KPI y tableros.
11. Tablero del proyecto:
    - Tarjetas: avance real vs plan, SPI, CPI, costo real, hitos a tiempo, atrasadas.
    - Curva S (PV / EV / AC), avance por etapa, tabla de atrasos, carga de recursos y alertas.
    - Filtros: etapa, responsable, fecha de corte. Actualización dinámica.
12. Tablero de gestión del cambio: estados, solicitudes por etapa del flujo, matriz de riesgo, tiempos por etapa, adopción, consumo de contingencia y alertas, con filtros.
13. Usuarios y roles:
    - Administrador (Jefe de Proyecto): todo.
    - Integrante: registra avance y fechas reales solo de sus tareas, crea solicitudes de cambio y consulta Gantt y tableros. No edita planificación, KPI ni aprueba cambios.
    - La interfaz oculta acciones según el rol y el backend también lo valida.
14. Verificación del caso de prueba: checklist automático de la evidencia mínima (sección 1) con conteos reales desde la base, y guion de los 3 escenarios de la demo con antes y después.

## 6. Datos de prueba (seeds)
- Seed A, "Horizonte Conecta": convertido desde insumos/Caso3_Horizonte_Planificacion_Gantt.xlsx; 52 elementos entre subactividades e hitos, costo base $212.809.000. Añade al menos un vínculo SS, uno FF y uno SF; mi cronograma original solo tiene FS. Fecha de corte de ejemplo: 15-01-2027, con avance real simulado y coherente.
- Seed B, "Caso de prueba mínimo": exactamente 4 etapas, 12 actividades, 20 subactividades, los 4 tipos de dependencia, 5 profesionales, 4 tipos de recursos, 6 hitos con criterios, 5 solicitudes de cambio en distintas etapas, 8 + 12 KPI. Entrégalo también como .xlsx en el formato de la plantilla, para importarlo en la demo.
- Todos los seeds y archivos generados se guardan en seeds/, nunca en insumos/.
- Script para resetear la base y cargar los seeds con un comando.

## 7. Modelo de datos mínimo
Proyecto, Calendario/Feriado, ElementoGantt (jerarquía por padre_id), Dependencia (tipo, desfase), Recurso/Trabajador, TipoRecurso, Asignación, RegistroAvance (por corte), CostoReal, Hito, CriterioAceptación (+ evidencia), HitoTarea, LíneaBase + SnapshotLíneaBase, KPI, VariableKPI, VersiónFórmula, ValorKPI (histórico), SolicitudCambio, EtapaFlujo, TransiciónSolicitud (bitácora), ImpactoCambio, Evidencia (archivo), Usuario, Rol, Auditoría.

Reglas de integridad:
- No eliminar elementos con dependencias o asignaciones sin confirmarlo.
- Las líneas base son inmutables.
- Toda transición de una solicitud queda registrada.

Entregar diagrama ER en docs/.

## 8. IA opcional (con API key)
- Integración desacoplada, compatible con API estilo OpenAI y con Anthropic.
- Configuración por variables de entorno en .env: LLM_PROVIDER, LLM_API_KEY, LLM_MODEL. El .env va en .gitignore; se incluye .env.example.
- Si no hay key, la función se oculta y nada se rompe.
- Usos:
  - (a) Sugerir el mapeo de columnas cuando el Excel no sigue la plantilla.
  - (b) Redactar el resumen del análisis de impacto de una solicitud.
  - (c) Resumen ejecutivo en lenguaje natural de los tableros y alertas.
  - (d) Sugerir criterios de aceptación para un hito.
- Reglas:
  - La IA NUNCA calcula KPI, fechas ni costos: eso lo hace el motor.
  - La IA nunca modifica datos sin confirmación del usuario.
  - La key solo vive en el backend.
  - Timeout y respuesta de respaldo.
  - Registrar uso y costo.

## 9. Stack sugerido (decídelo con ADR; compatible con Lemoria y pytest)
- Backend: Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic, openpyxl/pandas para importar y exportar, parser de fórmulas seguro (p. ej. una gramática propia o "simpleeval" restringido), JWT con roles.
- Base de datos: PostgreSQL 16 separada de la de Lemoria ("trazo_db").
- Frontend: React + TypeScript + Vite, TanStack Query, librería de gráficos (Recharts o similar).
  - La Gantt debe ser un componente SVG propio, o una librería que soporte FS/SS/FF/SF, línea base y jerarquía. Justifícalo en el ADR.
- Docker Compose (con "name: trazo") para levantar app + base con un comando.
- Exportar: Gantt y tableros a PDF/PNG (deseable); datos a .xlsx en el mismo formato de la plantilla.

## 10. Requisitos no funcionales
- Persistencia real: nada solo en memoria del navegador.
- Validaciones en backend.
- Respuestas de recálculo en menos de 1 s para unas 100 tareas.
- Interfaz en español; fechas dd-mm-aaaa; moneda CLP con separador de miles.
- Usable en notebook (1366 px) sin scroll horizontal de página.
- Código con tipado, linters y tests en CI (GitHub Actions).
- Rutas siempre entre comillas, porque la carpeta raíz tiene espacios.

## 11. Documentación y entregables (en docs/, salvo README.md en la raíz)
- README: instalación, seeds y cómo correr la demo.
- Documento técnico: requerimientos por módulo, modelo de datos, API (OpenAPI), motor de cálculo con fórmulas, formato del archivo de entrada y ADRs.
- Manual de usuario por rol.
- Plantilla .xlsx con instrucciones (en seeds/ o docs/plantillas/).
- Guion de la demostración (los 3 escenarios con resultados esperados).
- Matriz de trazabilidad: requisito → tarea → test → indicador de la rúbrica.

## 12. Plan de trabajo esperado (Tasks)
Divide en fases con hitos y tareas atómicas (ID, agente responsable, dependencia, criterio de aceptación, indicador de rúbrica):
- F0: setup de la carpeta "ev2 gestion de software", git, Docker, CI, ADRs.
- F1: modelo de datos y migraciones.
- F2: importador + plantilla + conversor de Horizonte + seeds.
- F3: motor de programación y costos + tests.
- F4: API.
- F5: Gantt y actividades.
- F6: recursos y costos.
- F7: hitos y criterios.
- F8: KPI y parser.
- F9: gestión del cambio y líneas base.
- F10: tableros.
- F11: roles y auditoría.
- F12: IA opcional.
- F13: verificación del caso de prueba + guion de demo + documentación.

El corte vertical mínimo debe estar funcionando al terminar F5.

## 13. Definición de terminado
- Los 3 escenarios de la demo funcionan sobre ambos seeds y se ven sus efectos en Gantt, costos, KPI y tableros.
- El checklist de evidencia mínima está en verde.
- Tests pasando y review-agent sin hallazgos críticos.
- Documentación al día, insumos/ intacta y memoria de Lemoria actualizada.

## 14. Preguntas abiertas (pregúntamelas en Discovery)
1. ¿Las 10 etapas del flujo de cambio y los 3 KPI adicionales coinciden con los que definió el docente?
2. ¿Fecha de entrega y fecha de la demostración?
3. ¿Despliegue: solo local con Docker o también en la nube?
4. ¿Proveedor de IA y modelo, si usaremos la función opcional?
