"""Database connection foundation.

Provides SQLAlchemy engine and session factory for PostgreSQL.
No domain models or tables are defined in v0.1 — this module
establishes the connection infrastructure only.
"""

from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from railgati.config import get_settings


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all future models."""


def get_engine(database_url: str | None = None) -> Engine:
    """Create a SQLAlchemy engine.

    Args:
        database_url: PostgreSQL connection URL. Falls back to settings if not provided.
    """
    url = database_url or get_settings().database_url
    return create_engine(url, pool_pre_ping=True)


def get_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    """Create a session factory bound to the engine.

    Args:
        database_url: PostgreSQL connection URL. Falls back to settings if not provided.
    """
    engine = get_engine(database_url)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    """Yield a database session for FastAPI dependency injection.

    Usage::

        @router.get("/example")
        def example(db: Session = Depends(get_db)):
            ...
    """
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
