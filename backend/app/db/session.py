"""SQLAlchemy session management for Aegis Vuldris."""

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy.orm import Session, sessionmaker

from app.db.engine import get_database_engine


@lru_cache
def create_session_factory() -> sessionmaker[Session]:
    """Return the shared SQLAlchemy session factory."""

    return sessionmaker(
        bind=get_database_engine(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


def get_db_session() -> Generator[Session, None, None]:
    """Yield a database session and close it after use."""

    session = create_session_factory()()

    try:
        yield session
    finally:
        session.close()
