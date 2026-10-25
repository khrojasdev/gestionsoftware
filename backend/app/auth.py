"""Authentication and role-based authorization for the Trazo API."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import User

ROLE_ADMIN = "ADMINISTRADOR"
ROLE_PROJECT_MANAGER = "JEFE_DE_PROYECTO"
ROLE_MEMBER = "INTEGRANTE"
MANAGEMENT_ROLES = (ROLE_ADMIN, ROLE_PROJECT_MANAGER)
ALL_ROLES = (ROLE_ADMIN, ROLE_PROJECT_MANAGER, ROLE_MEMBER)

_PASSWORD_SCHEME = "pbkdf2_sha256"
_PASSWORD_ITERATIONS = 600_000
_bearer = HTTPBearer(auto_error=False)
_credentials_dependency = Depends(_bearer)
_db_dependency = Depends(get_db)


def _auth_secret() -> str:
    """Return the configured signing key and fail closed when it is absent."""

    secret = get_settings().auth_secret
    if not secret:
        raise RuntimeError("AUTH_SECRET no está configurado")
    return secret


def normalize_role_name(name: str) -> str:
    """Normalize the public role vocabulary while accepting common aliases."""

    aliases = {
        "ADMIN": ROLE_ADMIN,
        "ADMINISTRATOR": ROLE_ADMIN,
        "PROJECT_MANAGER": ROLE_PROJECT_MANAGER,
        "PROJECT MANAGER": ROLE_PROJECT_MANAGER,
        "MEMBER": ROLE_MEMBER,
    }
    normalized = name.strip().upper()
    return aliases.get(normalized, normalized)


def hash_password(password: str) -> str:
    """Hash a password using a salted, deliberately expensive KDF."""

    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PASSWORD_ITERATIONS)
    encode = base64.urlsafe_b64encode
    return f"{_PASSWORD_SCHEME}${_PASSWORD_ITERATIONS}${encode(salt).decode()}${encode(digest).decode()}"


def verify_password(password: str, encoded_hash: str) -> bool:
    """Verify a password without exposing whether the stored hash matched."""

    try:
        scheme, iterations_text, salt_text, digest_text = encoded_hash.split("$", 3)
        if scheme != _PASSWORD_SCHEME:
            return False
        iterations = int(iterations_text)
        salt = base64.urlsafe_b64decode(salt_text.encode())
        expected = base64.urlsafe_b64decode(digest_text.encode())
    except (binascii.Error, TypeError, ValueError, UnicodeDecodeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return hmac.compare_digest(actual, expected)


def _encode_part(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_part(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_access_token(user: User) -> tuple[str, datetime]:
    """Create a short, signed token whose subject is the user UUID."""

    expires_at = datetime.now(UTC) + timedelta(minutes=get_settings().auth_token_ttl_minutes)
    payload = {"sub": str(user.id), "exp": int(expires_at.timestamp())}
    encoded_payload = _encode_part(json.dumps(payload, separators=(",", ":")).encode())
    signature = hmac.new(
        _auth_secret().encode(), encoded_payload.encode(), hashlib.sha256
    ).digest()
    return f"{encoded_payload}.{_encode_part(signature)}", expires_at


def _decode_access_token(token: str) -> UUID:
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
        expected_signature = hmac.new(
            _auth_secret().encode(), encoded_payload.encode(), hashlib.sha256
        ).digest()
        actual_signature = _decode_part(encoded_signature)
        if not hmac.compare_digest(actual_signature, expected_signature):
            raise ValueError("invalid signature")
        payload = json.loads(_decode_part(encoded_payload))
        if datetime.now(UTC).timestamp() >= float(payload["exp"]):
            raise ValueError("expired token")
        return UUID(str(payload["sub"]))
    except (binascii.Error, KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas o expiradas",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error


def role_names(user: User) -> list[str]:
    """Return stable role names for a user."""

    return sorted({role.name for role in user.roles})


def has_role(user: User, *required_roles: str) -> bool:
    granted = set(role_names(user))
    return bool(granted.intersection(required_roles))


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = _credentials_dependency,
    db: Session = _db_dependency,
) -> User:
    """Resolve and validate the authenticated active user."""

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticación requerida",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = _decode_access_token(credentials.credentials)
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario inactivo o inexistente",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_roles(*required_roles: str) -> Callable[..., User]:
    """Build a dependency that enforces at least one of the given roles."""

    current_user_dependency = Depends(get_current_user)

    def dependency(user: User = current_user_dependency) -> User:
        if not has_role(user, *required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El rol del usuario no permite esta operación",
            )
        return user

    return dependency
