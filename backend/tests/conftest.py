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
_TEST_DB_PATH = Path(__file__).resolve().parent / "wms_pytest.sqlite"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB_PATH}"

from app.db.session import SessionLocal, engine, get_db
from app.main import create_app
from app.models import Base
from app.services import inbound_intake_box_service as inbound_box_svc
from app.services import inbound_intake_service as inbound_intake_svc

# IN-BE-01: box service status tuples until IN-BE-02 updates the module.
inbound_box_svc.INTAKE_STATUSES = (inbound_intake_svc.STATUS_RECEIVING,)  # type: ignore[assignment]
inbound_box_svc.BOX_STATUSES_AFTER_PRIMARY = (  # type: ignore[assignment]
    inbound_intake_svc.STATUS_RECEIVING,
    inbound_intake_svc.STATUS_SORTING,
    inbound_intake_svc.STATUS_DONE,
)


@pytest_asyncio.fixture
async def async_client() -> AsyncIterator[AsyncClient]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with SessionLocal() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
