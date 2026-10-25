# ADR 0001: Stack local y separación de PostgreSQL

- **Estado:** aceptado
- **Fecha:** 2026-10-25
- **Tarea:** F0 Setup local, Docker y CI

## Contexto

Trazo debe ejecutarse en Windows 11, incluso cuando la carpeta del proyecto tiene espacios y Lemoria ya usa PostgreSQL. El entorno local debe ser reproducible y no debe guardar datos de PostgreSQL dentro de OneDrive.

## Decisión

- Backend en Python 3.12 con FastAPI, configuración mediante `pydantic-settings` y tests con pytest.
- Frontend en React + TypeScript + Vite.
- PostgreSQL 16 en un servicio Docker separado, con base `trazo_db`, usuario `trazo_app` y puerto del host `5433`.
- Compose usa explícitamente el nombre de proyecto `trazo` y volúmenes Docker nombrados.
- GitHub Actions ejecuta tests, Ruff, ESLint, TypeScript y build.

## Alternativas descartadas

- Usar el PostgreSQL de Lemoria: mezcla datos y dificulta resetear la aplicación de manera segura.
- Guardar `./data` en el repositorio: OneDrive puede sincronizar archivos de base de datos y producir corrupción o conflictos.
- Bash como requisito de desarrollo: no es la terminal disponible de forma predeterminada en Windows 11.
