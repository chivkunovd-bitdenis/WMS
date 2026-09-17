"""WMS-272: real PostgreSQL contention without creating or changing warehouse data."""

from __future__ import annotations

import asyncio
import os
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.services import marketplace_seller_lock_service as locks


@pytest.mark.asyncio
@pytest.mark.postgresql_concurrency
async def test_waiting_creates_release_pool_but_owner_keeps_same_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = os.environ.get("WMS_TEST_DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("requires explicit PostgreSQL test URL; uses advisory locks and SELECT only")
    # WMS-435: a session-scoped claim now holds its advisory lock on its own
    # private connection instead of the caller's (a leaked lock could no
    # longer survive the caller's commit otherwise). Each waiting caller here
    # keeps its own pre-lock connection (the "preview") *and* transiently
    # needs one more for its own lock polling, so two concurrent waiters need
    # up to 4 at once, plus one more for the unrelated probe below.
    engine = create_async_engine(url, pool_size=6, max_overflow=0, pool_timeout=1.0)
    owner_engine = create_async_engine(url, pool_size=1, max_overflow=0)
    sessions = async_sessionmaker(engine)
    owners = async_sessionmaker(owner_engine)
    seller_id = uuid.uuid4()
    sleeping = asyncio.Event()
    sleep_count = 0
    active = 0

    async def observed_sleep(delay: float) -> None:
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count >= 2:
            sleeping.set()
        await asyncio.sleep(delay)

    # Observe the actual polling boundary; advisory SQL and pool checkout stay real.
    monkeypatch.setattr(locks, "asyncio", SimpleNamespace(sleep=observed_sleep))

    async def waiting_create() -> int:
        nonlocal active
        async with sessions() as session:
            # The create path has already read its preview before entering the lock.
            await session.scalar(text("select 1"))
            async with locks.marketplace_seller_lock(
                session,
                seller_id,
                "wb",
                wait_timeout_sec=3.0,
                release_connection_while_waiting=True,
            ) as acquired:
                assert acquired
                assert active == 0
                active += 1
                pid = await session.scalar(text("select pg_backend_pid()"))
                await asyncio.sleep(0.03)  # stand-in for the active owner's HTTP wait
                assert await session.scalar(text("select pg_backend_pid()")) == pid
                active -= 1
            # The caller's own connection is never touched by the lock wrapper
            # (WMS-435): unlocking runs on the lock's private connection, so
            # this session's pid is unchanged before, during and after it.
            assert await session.scalar(text("select pg_backend_pid()")) == pid
            return int(pid)

    tasks: list[asyncio.Task[int]] = []
    try:
        async with owners() as owner:
            async with locks.marketplace_seller_lock(owner, seller_id, "wb") as acquired:
                assert acquired
                tasks = [asyncio.create_task(waiting_create()) for _ in range(2)]
                await asyncio.wait_for(sleeping.wait(), timeout=2.0)
                assert not any(task.done() for task in tasks)
                # Two waiting operators cannot exhaust this deliberately sized pool:
                # each one's own lock-polling connection is still given back between
                # attempts (WMS-435 R4г), so a third, unrelated screen gets through.
                async with sessions() as unrelated_screen:
                    assert await unrelated_screen.scalar(text("select 1")) == 1
            await asyncio.gather(*tasks)
            # A separate physical connection can take the lock: neither waiter leaked it.
            async with locks.marketplace_seller_lock(owner, seller_id, "wb") as acquired:
                assert acquired
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await engine.dispose()
        await owner_engine.dispose()
