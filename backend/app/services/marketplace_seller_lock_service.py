from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import monotonic

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_LOCK_NAMESPACE = b"wms:fbs:marketplace:seller:"


async def _session_uses_postgresql(session: AsyncSession) -> bool:
    connection = await session.connection()
    return connection.dialect.name == "postgresql"


def marketplace_seller_lock_key(seller_id: uuid.UUID, marketplace: str) -> int:
    provider = marketplace.strip().lower().encode("utf-8")
    digest = hashlib.blake2b(
        _LOCK_NAMESPACE + seller_id.bytes + b":" + provider,
        digest_size=8,
    ).digest()
    raw = int.from_bytes(digest, "big", signed=False)
    return raw - (1 << 64) if raw >= 1 << 63 else raw


async def acquire_marketplace_seller_lock(
    session: AsyncSession,
    seller_id: uuid.UUID,
    marketplace: str,
    *,
    wait_timeout_sec: float = 0.0,
    poll_interval_sec: float = 0.25,
) -> int | None:
    lock_key = marketplace_seller_lock_key(seller_id, marketplace)
    if not await _session_uses_postgresql(session):
        return lock_key
    deadline = monotonic() + max(wait_timeout_sec, 0.0)
    while True:
        acquired = await session.scalar(
            text("select pg_try_advisory_lock(:lock_key)"),
            {"lock_key": lock_key},
        )
        if acquired:
            return lock_key
        remaining = deadline - monotonic()
        if remaining <= 0:
            return None
        await asyncio.sleep(min(poll_interval_sec, remaining))


async def release_marketplace_seller_lock(session: AsyncSession, lock_key: int) -> None:
    if not await _session_uses_postgresql(session):
        return
    await session.scalar(
        text("select pg_advisory_unlock(:lock_key)"),
        {"lock_key": lock_key},
    )


@asynccontextmanager
async def marketplace_seller_lock(
    session: AsyncSession,
    seller_id: uuid.UUID,
    marketplace: str,
    *,
    wait_timeout_sec: float = 0.0,
) -> AsyncIterator[bool]:
    lock_key = await acquire_marketplace_seller_lock(
        session,
        seller_id,
        marketplace,
        wait_timeout_sec=wait_timeout_sec,
    )
    try:
        yield lock_key is not None
    finally:
        if lock_key is not None:
            await release_marketplace_seller_lock(session, lock_key)
