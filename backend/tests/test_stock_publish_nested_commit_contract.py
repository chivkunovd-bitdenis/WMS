"""R52/C66-C68: native transaction events defer stock publication to root commit."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.services import fbs_stock_publish_service as publisher

TENANT = uuid.UUID("11111111-1111-4111-8111-111111111111")
SELLER = uuid.UUID("22222222-2222-4222-8222-222222222222")
MARKETPLACE = "wb"


@pytest_asyncio.fixture
async def publication_boundary(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[AsyncSession, list[dict[str, Any]], list[str]]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'native-events.sqlite'}")
    async with engine.begin() as connection:
        await connection.execute(text("CREATE TABLE movement (id INTEGER PRIMARY KEY)"))
    calls: list[dict[str, Any]] = []
    phase = ["outer-open"]
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            def observe_dispatch(
                tenant_id: uuid.UUID, seller_id: uuid.UUID, marketplace: str | None = None,
            ) -> None:
                calls.append({
                    "tenant": tenant_id, "seller": seller_id, "marketplace": marketplace,
                    "phase": phase[0], "nested": session.sync_session.in_nested_transaction(),
                })

            monkeypatch.setattr(publisher, "_dispatch", observe_dispatch)
            yield session, calls, phase
    finally:
        await engine.dispose()


def queue_twice(session: AsyncSession) -> None:
    publisher.schedule_seller_stock_publish(session, TENANT, SELLER, MARKETPLACE)
    publisher.schedule_seller_stock_publish(session, TENANT, SELLER, MARKETPLACE)


async def commit_savepoint(session: AsyncSession, phase: list[str]) -> None:
    await session.execute(text("INSERT INTO movement VALUES (1)"))
    nested = await session.begin_nested()
    await session.execute(text("INSERT INTO movement VALUES (2)"))
    phase[0] = "nested-commit"
    await nested.commit()
    assert session.in_transaction(), "the native outer transaction is still open"
    assert not session.in_nested_transaction(), "the native SAVEPOINT really ended"


@pytest.mark.asyncio
async def test_c66_native_savepoint_commit_keeps_intent_without_dispatch(
    publication_boundary: Any,
) -> None:
    session, calls, phase = publication_boundary
    outer = await session.begin()
    queue_twice(session)
    await commit_savepoint(session, phase)
    print(f"C66 native dispatch trace: {calls!r}")
    assert calls == [], "SAVEPOINT commit must not dispatch while the outer document is open"
    assert session.info[publisher._PENDING_KEY] == {(TENANT, SELLER, MARKETPLACE)}
    await outer.rollback()


@pytest.mark.asyncio
async def test_c67_saved_nested_intent_dispatches_once_at_native_outer_commit(
    publication_boundary: Any,
) -> None:
    session, calls, phase = publication_boundary
    outer = await session.begin()
    queue_twice(session)
    await commit_savepoint(session, phase)
    await session.execute(text("INSERT INTO movement VALUES (3)"))
    phase[0] = "outer-commit"
    await outer.commit()
    print(f"C67 nested-to-root native dispatch trace: {calls!r}")
    assert calls == [{
        "tenant": TENANT, "seller": SELLER, "marketplace": MARKETPLACE,
        "phase": "outer-commit", "nested": False,
    }], "the original coalesced intent must dispatch once at the true outer commit"
    assert session.info[publisher._PENDING_KEY] == set()


@pytest.mark.asyncio
async def test_c67_ordinary_native_outer_commit_coalesces_duplicates_once(
    publication_boundary: Any,
) -> None:
    session, calls, phase = publication_boundary
    outer = await session.begin()
    await session.execute(text("INSERT INTO movement VALUES (1)"))
    queue_twice(session)
    assert calls == [], "scheduling alone does not publish"
    phase[0] = "outer-commit"
    await outer.commit()
    print(f"C67 ordinary native dispatch trace: {calls!r}")
    assert calls == [{
        "tenant": TENANT, "seller": SELLER, "marketplace": MARKETPLACE,
        "phase": "outer-commit", "nested": False,
    }]
    assert session.info[publisher._PENDING_KEY] == set()


@pytest.mark.asyncio
async def test_c68_native_outer_rollback_after_savepoint_never_dispatches(
    publication_boundary: Any,
) -> None:
    session, calls, phase = publication_boundary
    outer = await session.begin()
    queue_twice(session)
    await commit_savepoint(session, phase)
    phase[0] = "outer-rollback"
    await outer.rollback()
    print(f"C68 native dispatch trace: {calls!r}")
    assert calls == [], "a rolled-back outer document must never have dispatched publication"
    assert session.info[publisher._PENDING_KEY] == set()
