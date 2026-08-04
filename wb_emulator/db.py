"""SQLite engine and session helpers."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from wb_emulator.models import Base, SchemaVersion
from wb_emulator.settings import Settings, get_settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def sqlite_url(db_path: Path) -> str:
    return f"sqlite:///{db_path.expanduser().resolve()}"


def get_engine(settings: Settings | None = None) -> Engine:
    global _engine
    if _engine is None:
        cfg = settings or get_settings()
        db_path = cfg.db_path.expanduser()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            sqlite_url(db_path),
            connect_args={"check_same_thread": False},
        )
    return _engine


def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(settings),
            autoflush=False,
            autocommit=False,
        )
    return _session_factory


def get_db() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def init_db(settings: Settings | None = None) -> Path:
    """Create SQLite file and tables if missing."""
    cfg = settings or get_settings()
    engine = get_engine(cfg)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        has_row = session.scalar(select(SchemaVersion.id).limit(1)) is not None
        if not has_row:
            session.add(SchemaVersion(version=1))
            session.commit()

    return cfg.db_path.expanduser().resolve()


def reset_db_runtime() -> None:
    """Clear cached engine/session (tests only)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
