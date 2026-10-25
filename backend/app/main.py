"""HTTP entrypoint for the Trazo API."""

from fastapi import FastAPI, HTTPException
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
from app.config import get_settings
from app.routers import router as f8_router

settings = get_settings()
app = FastAPI(
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


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    """Report that the API process is ready to receive requests."""
    return {"status": "ok", "service": settings.app_name}
