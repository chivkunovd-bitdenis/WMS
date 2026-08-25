"""Backward-compatible WB names for marketplace-scoped advisory locks."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.marketplace_seller_lock_service import (
    acquire_marketplace_seller_lock,
    marketplace_seller_lock_key,
    release_marketplace_seller_lock,
)


def wb_seller_lock_key(seller_id: uuid.UUID) -> int:
    return marketplace_seller_lock_key(seller_id, "wb")


async def acquire_wb_seller_lock(
    session: AsyncSession,
    seller_id: uuid.UUID,
    *,
    wait_timeout_sec: float = 0.0,
    poll_interval_sec: float = 0.25,
) -> int | None:
    return await acquire_marketplace_seller_lock(
        session,
        seller_id,
        "wb",
        wait_timeout_sec=wait_timeout_sec,
        poll_interval_sec=poll_interval_sec,
    )


async def release_wb_seller_lock(session: AsyncSession, lock_key: int) -> None:
    await release_marketplace_seller_lock(session, lock_key)


@asynccontextmanager
async def wb_seller_lock(
    session: AsyncSession,
    seller_id: uuid.UUID,
    *,
    wait_timeout_sec: float = 0.0,
) -> AsyncIterator[bool]:
    lock_key = await acquire_wb_seller_lock(
        session, seller_id, wait_timeout_sec=wait_timeout_sec
    )
    try:
        yield lock_key is not None
    finally:
        if lock_key is not None:
            await release_wb_seller_lock(session, lock_key)
