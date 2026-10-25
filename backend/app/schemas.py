"""Pydantic request and response contracts for F8."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth import ALL_ROLES, normalize_role_name


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=200)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized:
            raise ValueError("Debe indicar un correo válido")
        return normalized


class RoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None


class UserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    is_active: bool
    roles: list[str]
    created_at: datetime


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserResponse


class UserCreateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    full_name: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=8, max_length=200)
    roles: list[str] = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized:
            raise ValueError("Debe indicar un correo válido")
        return normalized

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(normalize_role_name(value) for value in values))
        invalid = sorted(set(normalized) - set(ALL_ROLES))
        if invalid:
            raise ValueError(f"Roles no válidos: {', '.join(invalid)}")
        return normalized


class UserUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=160)
    password: str | None = Field(default=None, min_length=8, max_length=200)
    is_active: bool | None = None
    roles: list[str] | None = Field(default=None, min_length=1)

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        normalized = list(dict.fromkeys(normalize_role_name(value) for value in values))
        invalid = sorted(set(normalized) - set(ALL_ROLES))
        if invalid:
            raise ValueError(f"Roles no válidos: {', '.join(invalid)}")
        return normalized


class AuditResponse(BaseModel):
    id: UUID
    user_id: UUID | None
    action: str
    entity_type: str
    entity_id: UUID | None
    before_data: dict[str, Any] | None
    after_data: dict[str, Any] | None
    occurred_at: datetime
