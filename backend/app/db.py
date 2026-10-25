"""SQLAlchemy database primitives for the Trazo application database."""

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


@lru_cache
def get_engine():
    """Build one pooled engine per process.

    ``pool_pre_ping`` is intentional: the local PostgreSQL container can be
    restarted independently from the API process.
    """

    return create_engine(
        get_settings().database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
    )


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())


def get_db() -> Generator[Session, None, None]:
    """Yield a request-scoped session and always close it."""

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
