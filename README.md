# Trazo

Plataforma de planificación y control de proyectos basada en Carta Gantt.

## Requisitos

- Windows 11 con Docker Desktop y Docker Compose v2.
- Python 3.12+ para ejecutar el backend fuera de Docker.
- Node.js 20+ para ejecutar el frontend fuera de Docker.

## Inicio local con Docker

Desde la raíz del repositorio (la ruta puede contener espacios):

```powershell
Copy-Item ".env.example" ".env"
docker compose up --build
```

Servicios disponibles:

- Frontend: http://localhost:5173
- API y documentación OpenAPI: http://localhost:8000/docs
- Health check: http://localhost:8000/health
- PostgreSQL de Trazo: localhost:5433, base `trazo_db`

La base de datos de Trazo usa el volumen Docker nombrado `trazo_postgres_data` y es independiente de la base de datos de Lemoria.

Las migraciones Alembic se aplican automáticamente al iniciar el contenedor
`backend`. Para ejecutarlas manualmente fuera de Docker:

```powershell
python -m alembic -c "backend\alembic.ini" upgrade head
```

Para detener los servicios sin borrar datos:

```powershell
docker compose down
```

Para eliminar también el volumen local de PostgreSQL:

```powershell
docker compose down -v
```

## Desarrollo sin Docker

Backend:

```powershell
python -m venv ".venv"
& ".venv\Scripts\Activate.ps1"
python -m pip install -r "backend\requirements.txt"
python -m uvicorn app.main:app --reload --app-dir "backend"
```

Frontend:

```powershell
Set-Location "frontend"
npm install
npm run dev
```

## Calidad

```powershell
python -m pytest "backend\tests"
python -m ruff check "backend"
Set-Location "frontend"
npm run lint
npm run typecheck
npm run build
```

## Documentación y trazabilidad

- [Documentación técnica](docs/README.md)
- [Matriz F18: requisito → tarea → test → Ind.1–8](docs/matriz-trazabilidad.md)
- [Manual de usuario](docs/manual-usuario.md)
- [Guion de demo F9](docs/f9-guion-demo.md)
- [Guion manual F18](docs/f18-guion-trazabilidad.md)
- [ADR-007: Gantt, dependencias y decisión de no EDT](docs/adr/ADR-007-gantt-dependencias.md)

La jerarquía etapa → actividad → subactividad vive dentro de la Carta Gantt;
no existe un módulo EDT separado. La evidencia automática cubre tests de motor,
importación, API, integridad, roles, KPI y checklist. La revisión visual de los
tres escenarios se realiza con los guiones manuales. El repositorio no declara
una suite E2E de navegador ni una prueba automatizada que levante Docker completo;
Docker es el entorno local reproducible documentado.

Los insumos académicos en `insumos/` son de solo lectura y no son modificados por los scripts de desarrollo.
