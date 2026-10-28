"""HTTP entrypoint for the Trazo API (and, in production, the built web app)."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError

from app.api.errors import (
    ApiError,
    api_error_handler,
    domain_error_handler,
    integrity_error_handler,
    http_error_handler,
    unexpected_error_handler,
    validation_error_handler,
)
from app.api.f7 import router as f7_router
from app.api.routes import router
from app.api.views import router as views_router
from app.config import get_settings
from app.routers import router as f8_router

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Optionally load the demo data the first time the database is empty."""

    if os.environ.get("DEMO_SEED", "").strip().lower() in {"1", "true", "si", "sí", "yes"}:
        from app.demo import seed_if_empty

        seed_if_empty()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Trazo API",
    version="1.0.0",
    description="API versionada para planificación, control y cambio de proyectos.",
    openapi_url="/api/v1/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(router)
app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(HTTPException, http_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(IntegrityError, integrity_error_handler)
app.add_exception_handler(ValueError, domain_error_handler)
app.add_exception_handler(Exception, unexpected_error_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(f8_router)
app.include_router(f7_router)
app.include_router(views_router)


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    """Report that the API process is ready to receive requests."""
    return {"status": "ok", "service": settings.app_name}




STATIC_DIR = Path(os.environ.get("FRONTEND_DIST", Path(__file__).resolve().parents[1] / "static"))
if (STATIC_DIR / "index.html").exists():
    if (STATIC_DIR / "assets").exists():
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def single_page_app(full_path: str) -> FileResponse:
        """Serve the React build; unknown routes fall back to index.html."""

        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Recurso no encontrado")
        candidate = (STATIC_DIR / full_path).resolve()
        if full_path and candidate.is_file() and STATIC_DIR.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")
