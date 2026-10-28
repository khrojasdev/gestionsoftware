# Despliegue

Trazo se publica como **una sola imagen Docker** (`Dockerfile` en la raíz) que:

1. compila el frontend con Node 22;
2. instala la API en Python 3.12 y copia el frontend compilado y `seeds/`;
3. al arrancar ejecuta `alembic upgrade head` y luego `uvicorn` en el puerto `$PORT`
   (8000 por defecto);
4. si `DEMO_SEED=true` y la base está vacía, carga usuarios y proyectos de demostración.

Variables de entorno:

| Variable | Obligatoria | Descripción |
|---|---|---|
| `DATABASE_URL` | Sí | PostgreSQL. Acepta `postgres://…`, `postgresql://…` o `postgresql+psycopg://…` |
| `AUTH_SECRET` | Sí en producción | Clave de firma de sesiones, mínimo 32 caracteres |
| `APP_ENV` | No | `production` exige `AUTH_SECRET` |
| `DEMO_SEED` | No | `true` carga la demo si la base está vacía |
| `PORT` | No | Puerto HTTP (los proveedores lo definen solos) |
| `UPLOAD_DIR` | No | Carpeta de evidencias (por defecto `/app/data/uploads`) |
| `CORS_ORIGINS` | No | Solo si el frontend se sirve desde otro dominio |

Genera un `AUTH_SECRET` con:

```bat
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Render (recomendado, con blueprint)

1. Crear cuenta en https://render.com y conectar GitHub.
2. **New → Blueprint** → elegir el repositorio `gestionsoftware`.
3. Render lee `render.yaml`: crea la base `trazo-db` y el servicio web `trazo`,
   genera `AUTH_SECRET` y conecta `DATABASE_URL`.
4. Esperar el primer despliegue (5–8 min) y abrir la URL `https://trazo-xxxx.onrender.com`.

Notas del plan gratuito: el servicio se suspende tras 15 minutos sin uso (la primera
visita tarda ~1 minuto en despertar), la base gratuita caduca a los 30 días y el
disco del contenedor no es persistente (las evidencias subidas se pierden en cada
despliegue; las de la demo se regeneran como archivo de muestra).

## Railway

1. **New Project → Deploy from GitHub repo** → `gestionsoftware` (detecta el `Dockerfile`).
2. **New → Database → PostgreSQL**.
3. En el servicio web, variables: `DATABASE_URL=${{Postgres.DATABASE_URL}}`,
   `AUTH_SECRET=<clave>`, `APP_ENV=production`, `DEMO_SEED=true`.
4. **Settings → Networking → Generate Domain**.

## Servidor propio (VPS con Docker)

```bash
git clone https://github.com/khrojasdev/gestionsoftware.git
cd gestionsoftware
cp .env.example .env   # definir AUTH_SECRET, POSTGRES_PASSWORD y APP_ENV=production
docker compose up --build -d
```

Publicar el puerto 8000 detrás de un proxy con HTTPS (Caddy, Nginx o Traefik).

## Reiniciar la demostración en un despliegue

Desde la consola del servicio (Render «Shell», Railway «Run command») o con
`docker compose exec app`:

```bash
python -m app.demo --reset
```
