from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import Session, sessionmaker

from util.paths import sqlite_url

DB_NAME = "dnd.db"

_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker] = None


def get_engine() -> Engine:
    global _engine, _session_factory
    if _engine is None:
        _engine = create_engine(sqlite_url(DB_NAME))
        _session_factory = sessionmaker(bind=_engine)
    return _engine


def set_engine(engine: Engine) -> None:
    global _engine, _session_factory
    _engine = engine
    _session_factory = sessionmaker(bind=engine)


def reset_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


@contextmanager
def get_session() -> Generator[Session, None, None]:
    if _session_factory is None:
        get_engine()

    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
