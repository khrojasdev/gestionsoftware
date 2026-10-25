"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the API."""

    app_name: str = "trazo"
    app_env: str = "development"
    database_url: str = "postgresql+psycopg://trazo_app:trazo_local_password@localhost:5433/trazo_db"
    cors_origins: str = "http://localhost:5173"
    log_level: str = "INFO"
    auth_secret: str | None = None
    auth_token_ttl_minutes: int = 480

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_auth_secret(self) -> "Settings":
        """Require an explicitly provisioned signing key outside tests/local setup."""

        if self.app_env.casefold() in {"production", "staging", "prod"}:
            if not self.auth_secret or len(self.auth_secret) < 32:
                raise ValueError("AUTH_SECRET es obligatorio y debe tener al menos 32 caracteres")
        elif self.auth_secret is not None and len(self.auth_secret) < 32:
            raise ValueError("AUTH_SECRET debe tener al menos 32 caracteres")
        return self

    def allowed_origins(self) -> list[str]:
        """Return configured CORS origins as a normalized list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings."""
    return Settings()
