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

Los insumos académicos en `insumos/` son de solo lectura y no son modificados por los scripts de desarrollo.
