"""Stable error envelope and domain-to-HTTP translation."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """An expected client-facing application error."""

    def __init__(self, code: str, message: str, status_code: int = 400, details: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


def error_payload(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details}}


async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(content=error_payload(exc.code, exc.message, exc.details), status_code=exc.status_code)


async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [{"loc": list(error["loc"]), "message": error["msg"]} for error in exc.errors()]
    return JSONResponse(content=error_payload("VALIDATION_ERROR", "La solicitud no es válida", details), status_code=422)


async def http_error_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    """Keep framework/authentication failures in the same public envelope."""

    detail = exc.detail if isinstance(exc.detail, str) else "La solicitud no es válida"
    code = "AUTHENTICATION_REQUIRED" if exc.status_code == 401 else "FORBIDDEN" if exc.status_code == 403 else "HTTP_ERROR"
    return JSONResponse(content=error_payload(code, detail), status_code=exc.status_code)


async def integrity_error_handler(_request: Request, exc: IntegrityError) -> JSONResponse:
    logger.warning("Database integrity error", exc_info=exc)
    return JSONResponse(content=error_payload("CONFLICT", "La operación entra en conflicto con datos existentes"), status_code=409)


async def domain_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(content=error_payload("DOMAIN_ERROR", str(exc)), status_code=400)


async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled API error path=%s", request.url.path, exc_info=exc)
    return JSONResponse(content=error_payload("INTERNAL_ERROR", "Ocurrió un error interno"), status_code=500)
