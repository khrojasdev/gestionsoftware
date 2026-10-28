# Trazo: imagen única (frontend React compilado + API FastAPI).
# Sirve para Docker Desktop local y para desplegar en Render, Railway, Fly.io, etc.

# ---------- 1. Compilar el frontend ----------
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- 2. API + archivos estáticos ----------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FRONTEND_DIST=/app/backend/static \
    SEEDS_DIR=/app/seeds \
    UPLOAD_DIR=/app/data/uploads \
    PORT=8000
WORKDIR /app/backend
COPY backend/requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip && python -m pip install -r requirements.txt
COPY backend/ ./
COPY seeds/ /app/seeds/
COPY --from=web /web/dist /app/backend/static
RUN mkdir -p /app/data/uploads && useradd --create-home trazo && chown -R trazo /app
USER trazo
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health')"
CMD ["sh", "-c", "python -m alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
