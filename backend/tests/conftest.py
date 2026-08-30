from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# Before importing app.db.session: same DATABASE_URL for routes and BackgroundTasks.
os.environ.setdefault(
    "JWT_SECRET_KEY", "test-jwt-secret-key-at-least-32-characters-long"
)
_TEST_RUN_ID = os.environ.get("PYTEST_XDIST_WORKER", str(os.getpid()))
_TEST_DB_PATH = Path(__file__).resolve().parent / f"wms_pytest_{_TEST_RUN_ID}.sqlite"
_TEST_DATA_DIR = Path(__file__).resolve().parent / f"wms_pytest_data_{_TEST_RUN_ID}"
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
    """Схему строим один раз за прогон, между тестами только вычищаем строки.

    Снос и постройка 97 таблиц стоят 334 мс, очистка строк — 23 мс. На полном
    прогоне это разница между 16 и 3 минутами, при той же изоляции: тест всё
    так же начинает с пустой базы.

    Часть тестовых файлов сносит схему собственными фикстурами и не
    восстанавливает её. Поэтому очистку оборачиваем: пропала таблица —
    пересобираем схему и продолжаем.
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
