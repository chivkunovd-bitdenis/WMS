from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.settings import settings
from app.db.physical_warehouse_guard import register_sqlite_defect_function

engine: AsyncEngine = create_async_engine(settings.database_url, pool_pre_ping=True)
register_sqlite_defect_function(engine.sync_engine)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session

