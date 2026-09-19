"""
SQLAlchemy engine and session management for the content screening system.
"""

from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import Session, sessionmaker

from content_screening.constants import DB_NAME
from util.paths import sqlite_url

# Module-level engine instance (lazy-initialized)
_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker] = None


def get_engine() -> Engine:
    """Get the SQLAlchemy engine, creating it if necessary."""
    global _engine, _session_factory
    if _engine is None:
        _engine = create_engine(sqlite_url(DB_NAME))
        _session_factory = sessionmaker(bind=_engine)
    return _engine


def set_engine(engine: Engine) -> None:
    """Set a custom engine (for testing)."""
    global _engine, _session_factory
    _engine = engine
    _session_factory = sessionmaker(bind=engine)


def reset_engine() -> None:
    """Reset the engine to None (for testing)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Get a session context manager for database operations.

    Usage:
        with get_session() as session:
            session.add(obj)
            # commit happens automatically on successful exit
    """
    if _session_factory is None:
        get_engine()  # Initialize engine and session factory

    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
