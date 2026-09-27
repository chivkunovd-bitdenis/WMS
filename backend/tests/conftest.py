from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

# Before importing app.db.session: same DATABASE_URL for routes and BackgroundTasks.
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long")
# Регистрация организации на бою закрыта (WMS-383). Тесты заводят тенанты именно
# через неё, поэтому в тестовом окружении ручка включена явно.
os.environ.setdefault("WMS_ALLOW_PUBLIC_REGISTRATION", "true")
_TEST_RUN_ID = "_".join(
    (
        os.environ.get("PYTEST_XDIST_TESTRUNUID", str(os.getpid())),
        os.environ.get("PYTEST_XDIST_WORKER", "main"),
    )
)
_TEST_DB_PATH = Path(__file__).resolve().parent / f"wms_pytest_{_TEST_RUN_ID}.sqlite"
_TEST_DATA_DIR = Path(__file__).resolve().parent / f"wms_pytest_data_{_TEST_RUN_ID}"
if explicit_test_url := os.environ.get("WMS_TEST_DATABASE_URL"):
    test_url = make_url(explicit_test_url)
    if test_url.get_backend_name() == "postgresql" and (
        test_url.host not in {"localhost", "127.0.0.1", "::1", "postgres"}
        or not (test_url.database or "").startswith("wms_test")
    ):
        raise RuntimeError("PostgreSQL tests require an isolated loopback/CI wms_test database")
os.environ["DATABASE_URL"] = os.environ.get(
    "WMS_TEST_DATABASE_URL",
    f"sqlite+aiosqlite:///{_TEST_DB_PATH}",
)
os.environ["WMS_DATA_DIR"] = os.environ.get("WMS_TEST_DATA_DIR", str(_TEST_DATA_DIR))

from app.db.session import SessionLocal, engine, get_db
from app.main import create_app
from app.models import Base
from app.services.fbs_stock_publish_service import drain_background_stock_publish_tasks
from app.services.fbs_stock_sync_service import drain_zero_publish_background_tasks

_SCHEMA_READY = False


async def _rebuild_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


async def _reset_database() -> None:
    """Build each worker's schema once, then clear rows between tests.

    API and direct service fixtures share this path and drain background work
    before resetting. Rebuild only if a test deliberately removed schema.
    """
    global _SCHEMA_READY
    from sqlalchemy import text as _sql_text
    from sqlalchemy.exc import OperationalError, ProgrammingError

    if not _SCHEMA_READY:
        await _rebuild_schema()
        _SCHEMA_READY = True
        return
    try:
        async with engine.begin() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                await conn.execute(_sql_text(f'DELETE FROM "{table.name}"'))
    except (OperationalError, ProgrammingError):
        await _rebuild_schema()


@pytest_asyncio.fixture
async def async_client() -> AsyncIterator[AsyncClient]:
    await drain_background_stock_publish_tasks()
    await drain_zero_publish_background_tasks()
    await _reset_database()

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with SessionLocal() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    await drain_background_stock_publish_tasks()
    await drain_zero_publish_background_tasks()
    await _reset_database()


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Use the same isolated schema and task cleanup as API tests (WMS-365)."""
    await drain_background_stock_publish_tasks()
    await drain_zero_publish_background_tasks()
    await _reset_database()
    async with SessionLocal() as session:
        yield session
    await drain_background_stock_publish_tasks()
    await drain_zero_publish_background_tasks()


@pytest.fixture(autouse=True)
def isolated_login_rate_limit():
    from app.services.login_rate_limit import (
        configure_for_tests,
        get_config,
        reset_rate_limit_state,
    )

    original = get_config()
    reset_rate_limit_state()
    yield
    reset_rate_limit_state()
    configure_for_tests(max_attempts=original[0], window_seconds=original[1])


@pytest_asyncio.fixture
async def db_session_with_foreign_keys(db_session: AsyncSession) -> AsyncIterator[AsyncSession]:
    """Pin SQLite FK enforcement across commits without changing other pooled connections.

    PRAGMA foreign_keys is connection-local, not session-local. A session bound to
    an engine releases its connection on commit, so setting PRAGMA once on that
    session is insufficient when another test has grown the connection pool.
    PostgreSQL always enforces these constraints and needs no special connection.
    """
    if engine.dialect.name != "sqlite":
        yield db_session
        return
    async with engine.connect() as connection:
        original = (await connection.exec_driver_sql("PRAGMA foreign_keys")).scalar_one()
        await connection.commit()
        await connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        await connection.commit()
        try:
            async with AsyncSession(bind=connection, expire_on_commit=False) as guarded:
                yield guarded
        finally:
            await connection.rollback()
            await connection.exec_driver_sql(f"PRAGMA foreign_keys={int(original)}")
            await connection.commit()
