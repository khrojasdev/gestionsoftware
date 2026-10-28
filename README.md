# Trazo · Planificación y control de proyectos

Aplicación web para el **Caso 3 · Constructora Horizonte («Horizonte Conecta»)**
de Gestión de Proyectos de Software (Duoc UC). Importa la Carta Gantt, calcula
fechas, ruta crítica y costos, controla hitos y KPI, y gestiona solicitudes de
cambio con un flujo de 10 etapas que genera nuevas líneas base.

- **Frontend:** React 19 + TypeScript + Vite (sin librerías de gráficos: Gantt y gráficos en SVG propio).
- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic.
- **Base de datos:** PostgreSQL 16.
- **Un solo contenedor** sirve la API y la aplicación web compilada.

## Inicio rápido en Windows (Docker Desktop)

Requisitos: Docker Desktop iniciado. No necesitas Python ni Node para esta opción.

1. Abre la carpeta del repositorio.
2. Haz doble clic en **`iniciar-trazo.bat`** (o en CMD: `docker compose up --build -d`).
3. La primera vez tarda unos minutos (descarga imágenes, compila y carga la demo).
   Se abre solo `http://localhost:8000`.

| Usuario | Rol | Qué puede hacer |
|---|---|---|
| `admin@trazo.cl` | Administrador | Todo, incluido gestionar usuarios y eliminar proyectos |
| `kevin.henriquez@trazo.cl` | Jefe de Proyecto | Importar, planificar, recursos, KPI, aprobar y aplicar cambios |
| `diego.lopez@trazo.cl` | Integrante | Registrar avance de sus tareas, crear solicitudes, consultar |
| `christian.perez@trazo.cl` | Integrante | Igual que el anterior |

Contraseña de todos: **`Trazo2026!`** (la pantalla de ingreso tiene botones para completarla).

Otros archivos útiles en la raíz:

- `detener-trazo.bat` – detiene los contenedores (los datos se conservan).
- `reiniciar-demo.bat` – borra los proyectos y vuelve a cargar la demostración
  (en la web: Administrador → Proyectos → **Restaurar demo**).
- `docker compose logs -f app` – ver registros si algo falla.
- `docker compose down -v` – borrar también la base de datos.

> Si la carpeta está en OneDrive, pausa la sincronización mientras trabajas o
> mueve el repositorio fuera de OneDrive: la sincronización puede bloquear archivos
> de `node_modules` y del volumen.

## Datos de demostración

Al iniciar con la base vacía se cargan dos proyectos:

1. **Horizonte Conecta** (desde `insumos/Caso3_Horizonte_Planificacion_Gantt.xlsx`, o
   `seeds/Horizonte_Conecta_Carta_Gantt.xlsx` si no está): 10 etapas, 25 actividades,
   42 subactividades, 10 hitos, 14 profesionales y 9 recursos no humanos, fecha de
   corte 15‑01‑2027, línea base v2, 5 solicitudes de cambio (SC‑01 a SC‑05) en distintas
   etapas, 20 KPI y su historial semanal.
2. **Caso de prueba mínimo · App de inspecciones** (`seeds/Seed_B_Caso_Prueba_Minimo.xlsx`):
   cumple exactamente la evidencia mínima de la rúbrica (4 tipos de precedencia, 5
   profesionales, recursos no humanos, 6 hitos, 5 solicitudes).

La pantalla **Caso de prueba** muestra el checklist automático y el guion de los
3 escenarios. El guion completo está en [docs/guion-demo.md](docs/guion-demo.md).

## Cargar tu propia planificación

En **Importar Carta Gantt** sube la plantilla (`Descargar plantilla .xlsx`) llena con
tus datos o el libro del curso. Antes de confirmar puedes cambiar el código y el
nombre; si el código ya existe eliges entre **crear un proyecto nuevo** o
**reemplazar** la planificación existente. El sistema calcula
fechas, ruta crítica, costos, línea base, carga de recursos y KPI; si el archivo no
trae KPI ni etapas de cambio, crea los 20 KPI y el flujo de 10 etapas estándar.

## Pantallas

| # | Pantalla | Contenido |
|---|---|---|
| 01 | Proyectos | Tarjetas con avance real vs plan, SPI/CPI, término proyectado, crear/editar/cerrar |
| 02 | Importar Carta Gantt | Arrastrar archivo → revisión de hojas y columnas → validación → confirmar; descarga de plantilla |
| 03 | Actividades y precedencias | Tabla filtrable, editor de duración, precedencias FS/SS/FF/SF con desfase, avance real; muestra el antes/después del recálculo |
| 04 | Carta Gantt | Jerarquía plegable, plan vs línea base vs proyección, hitos, fecha de corte, flechas de precedencia, ruta crítica, zoom |
| 05 | Recursos y costos | Por recurso, por tarea (horas, h/día, costo), carga semanal con detalle, sobreasignaciones, costos por tipo y etapa, calendario |
| 06 | Hitos | Línea de tiempo, tareas del hito y criterios de aceptación con evidencias (acordeón) |
| 07 | Administrador de KPI | Fórmula visible y editable, sustitución de valores, variables, umbrales, prueba de fórmula, versiones, tendencia |
| 08 | Solicitudes de cambio | Listado, filtros y registro; detalle con 10 etapas, SLA, propuesta, simulación de impacto, aprobación, aplicación y trazabilidad |
| 09 | Tablero del proyecto | Avance, EVM, curva S, avance por etapa, KPI, alertas, atrasos, hitos y carga |
| 10 | Tablero del cambio | Embudo, tiempos vs SLA, matriz impacto × probabilidad, KPI C01–C12, alertas |
| 11 | Usuarios y roles | Administración de usuarios y matriz de permisos de los 3 roles |
| 12 | Caso de prueba | Checklist de evidencia mínima y guion de escenarios |

## Desarrollo sin Docker

```bat
:: Base de datos (solo el contenedor de PostgreSQL)
docker compose up -d db

:: Backend (CMD, desde la raíz)
python -m venv .venv
.venv\Scripts\activate
pip install -r backend\requirements.txt
copy .env.example backend\.env
:: edita backend\.env y define AUTH_SECRET (mínimo 32 caracteres)
cd backend
python -m alembic upgrade head
python -m app.demo
python -m uvicorn app.main:app --reload

:: Frontend (otra ventana, desde la raíz)
cd frontend
npm install
npm run dev
```

El frontend de desarrollo queda en `http://localhost:5173` y envía `/api` al
backend en `http://localhost:8000` (proxy de Vite). La documentación interactiva
de la API está en `http://localhost:8000/docs`.

## Despliegue

El `Dockerfile` de la raíz construye una imagen única. Instrucciones para Render
(blueprint `render.yaml`), Railway u otro servidor en
[docs/despliegue.md](docs/despliegue.md).

## Calidad

```bat
cd backend
ruff check .
pytest
:: Pruebas de integración con PostgreSQL (recargan la demo; no usar con datos reales)
set TRAZO_DB_TESTS=1
pytest

cd ..\frontend
npm run lint
npm run typecheck
npm run build
```

La integración continua (`.github/workflows/ci.yml`) ejecuta lint, pruebas unitarias,
pruebas de integración contra PostgreSQL (los 3 escenarios, permisos, ciclos y
criterios de hitos), la compilación del frontend y la construcción de la imagen Docker.

## Estructura

```
backend/        API FastAPI, motor de cálculo, importador, migraciones y pruebas
frontend/       Aplicación React
seeds/          Datos de demostración y plantilla de importación
insumos/        Documentos del curso (solo lectura)
docs/           Manual, guion de demo, despliegue y documentación técnica
Dockerfile      Imagen única (frontend compilado + API)
docker-compose.yml  PostgreSQL + aplicación para uso local
render.yaml     Blueprint para Render
```

## Documentación

- [Manual de usuario](docs/manual-usuario.md)
- [Guion de la demostración](docs/guion-demo.md)
- [Despliegue](docs/despliegue.md)
- [Importación de la Carta Gantt](docs/importacion-carta-gantt.md)
- [Modelo de datos](docs/modelo-datos.md)
- [Matriz de trazabilidad](docs/matriz-trazabilidad.md)
- [Decisiones de arquitectura](docs/adr/)

La jerarquía etapa → actividad → subactividad → hito vive dentro de la Carta Gantt;
no existe un módulo EDT separado (ver ADR‑007).
