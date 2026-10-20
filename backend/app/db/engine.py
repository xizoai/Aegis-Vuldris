"""SQLAlchemy engine configuration for Aegis Vuldris."""

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.core.config import get_settings


@lru_cache
def get_database_engine() -> Engine:
    """Return the shared SQLAlchemy engine for the application."""

    settings = get_settings()

    if not settings.database_url.strip():
        raise RuntimeError("DATABASE_URL must be configured before creating the database engine.")

    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
    )
