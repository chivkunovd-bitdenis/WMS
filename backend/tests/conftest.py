from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
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

# Схема создаётся один раз на прогон, а между тестами таблицы просто чистятся.
#
# Раньше каждый тест сносил и заново создавал все 97 таблиц, причём дважды — до и
# после себя. Это около двухсот операций над схемой на один тест; замер на этой
# машине дал 4.8 секунды подготовки против 0.2 секунды на очистку. На тысяче с
# лишним тестов разница — полтора часа против четырёх минут, и всё это время
# уходило не на проверку кода, а на пересоздание пустых таблиц.
#
# Порядок очистки обратный порядку создания, плюс отложенные внешние ключи:
# иначе удаление родителя раньше ребёнка упирается в ссылку.
_TRUNCATE_ORDER = list(reversed(Base.metadata.sorted_tables))


async def _reset_tables() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA defer_foreign_keys=ON"))
        for table in _TRUNCATE_ORDER:
            await conn.execute(text(f'DELETE FROM "{table.name}"'))


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _schema() -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def async_client() -> AsyncIterator[AsyncClient]:
    await drain_background_stock_publish_tasks()
    await drain_zero_publish_background_tasks()
    await _reset_tables()

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
    await _reset_tables()
