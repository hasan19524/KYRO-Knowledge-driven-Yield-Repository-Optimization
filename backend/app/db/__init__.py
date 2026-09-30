from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app import config


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory: sessionmaker[Session] | None = None


def get_engine(url: str | None = None):
    global _engine
    if _engine is None or (url is not None and str(_engine.url) != url):
        target = url or config.DATABASE_URL
        _engine = create_engine(
            target, pool_pre_ping=True, pool_size=5, max_overflow=10
        )
        _session_factory = None
    return _engine


def get_session_factory(url: str | None = None) -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None or url is not None:
        factory = sessionmaker(bind=get_engine(url), expire_on_commit=False)
        if url is None:
            _session_factory = factory
        return factory
    return _session_factory


def reset_engine() -> None:
    """Drop cached engine/session factory (used by tests)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
