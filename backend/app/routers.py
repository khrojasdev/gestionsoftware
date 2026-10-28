"""F8 users, roles, authentication and audit HTTP endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.audit import record_audit
from app.auth import (
    MANAGEMENT_ROLES,
    ROLE_ADMIN,
    create_access_token,
    get_current_user,
    has_role,
    hash_password,
    require_roles,
    role_names,
    verify_password,
)
from app.db import get_db
from app.models import AuditLog, Role, User
from app.schemas import (
    AuditResponse,
    LoginRequest,
    LoginResponse,
    RoleResponse,
    UserCreateRequest,
    UserResponse,
    UserUpdateRequest,
)

router = APIRouter(prefix="/api/v1", tags=["F8 usuarios y auditoría"])
DbSession = Annotated[Session, Depends(get_db)]
Manager = Annotated[User, Depends(require_roles(*MANAGEMENT_ROLES))]
Admin = Annotated[User, Depends(require_roles(ROLE_ADMIN))]


def user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        roles=role_names(user),
        created_at=user.created_at,
    )


def _roles_by_name(db: Session, names: list[str]) -> list[Role]:
    roles = list(db.scalars(sa.select(Role).where(Role.name.in_(names))).all())
    if len(roles) != len(set(names)):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Rol inexistente")
    return roles


def _ensure_admin_grant(actor: User, names: list[str]) -> None:
    if ROLE_ADMIN in names and not has_role(actor, ROLE_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo un Administrador puede otorgar el rol Administrador",
        )


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: DbSession) -> LoginResponse:
    user = db.scalar(
        sa.select(User).options(selectinload(User.roles)).where(User.email == payload.email)
    )
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token, expires_at = create_access_token(user)
    record_audit(
        db,
        user_id=user.id,
        action="LOGIN",
        entity_type="USER",
        entity_id=user.id,
        after_data={"email": user.email},
    )
    db.commit()
    return LoginResponse(
        access_token=token, expires_at=expires_at, user=user_response(user)
    )


@router.get("/auth/me", response_model=UserResponse)
def me(user: Annotated[User, Depends(get_current_user)]) -> UserResponse:
    return user_response(user)


@router.get("/roles", response_model=list[RoleResponse])
def list_roles(db: DbSession, _: Annotated[User, Depends(get_current_user)]) -> list[Role]:
    return list(db.scalars(sa.select(Role).order_by(Role.name)).all())


@router.get("/users", response_model=list[UserResponse])
def list_users(
    db: DbSession,
    _: Manager,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[UserResponse]:
    users = db.scalars(
        sa.select(User)
        .options(selectinload(User.roles))
        .order_by(User.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return [user_response(user) for user in users]


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreateRequest, db: DbSession, actor: Admin) -> UserResponse:
    _ensure_admin_grant(actor, payload.roles)
    roles = _roles_by_name(db, payload.roles)
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        roles=roles,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El correo ya existe") from error
    record_audit(
        db,
        user_id=actor.id,
        action="CREATE",
        entity_type="USER",
        entity_id=user.id,
        after_data={"email": user.email, "roles": payload.roles},
    )
    db.commit()
    db.refresh(user)
    return user_response(user)


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: UUID, payload: UserUpdateRequest, db: DbSession, actor: Admin
) -> UserResponse:
    user = db.scalar(sa.select(User).options(selectinload(User.roles)).where(User.id == user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    requested_roles = payload.roles if payload.roles is not None else role_names(user)
    _ensure_admin_grant(actor, requested_roles)
    before = {"full_name": user.full_name, "is_active": user.is_active, "roles": role_names(user)}
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.roles is not None:
        user.roles = _roles_by_name(db, payload.roles)
    after = {"full_name": user.full_name, "is_active": user.is_active, "roles": requested_roles}
    record_audit(
        db,
        user_id=actor.id,
        action="UPDATE",
        entity_type="USER",
        entity_id=user.id,
        before_data=before,
        after_data=after,
    )
    db.commit()
    db.refresh(user)
    return user_response(user)


@router.get("/audit-logs", response_model=list[AuditResponse])
def list_audit_logs(
    db: DbSession,
    _: Manager,
    action: str | None = Query(default=None, max_length=80),
    entity_type: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[AuditLog]:
    query = sa.select(AuditLog).order_by(AuditLog.occurred_at.desc()).offset(offset).limit(limit)
    if action:
        query = query.where(AuditLog.action == action.strip().upper())
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type.strip().upper())
    return list(db.scalars(query).all())
