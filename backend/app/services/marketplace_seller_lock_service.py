from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import monotonic

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

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
    release_connection_while_waiting: bool = False,
    transaction_scoped: bool = False,
) -> int | None:
    """Acquire the seller lock; opt-in callers must have only read-only work pending.

    A failed try-lock owns no advisory lock, so those callers can end their
    read transaction before sleeping. Once acquired, the connection must stay
    checked out until release_marketplace_seller_lock unlocks that same session.
    A transaction-scoped claim uses the same key but lasts until commit/rollback;
    its durable writes and unlock happen atomically, without an explicit unlock.
    """
    lock_key = marketplace_seller_lock_key(seller_id, marketplace)
    if not await _session_uses_postgresql(session):
        return lock_key
    deadline = monotonic() + max(wait_timeout_sec, 0.0)
    while True:
        statement = (
            "select pg_try_advisory_xact_lock(:lock_key)"
            if transaction_scoped
            else "select pg_try_advisory_lock(:lock_key)"
        )
        acquired = await session.scalar(
            text(statement),
            {"lock_key": lock_key},
        )
        if acquired:
            return lock_key
        if release_connection_while_waiting:
            await session.rollback()
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
    release_connection_while_waiting: bool = False,
    transaction_scoped: bool = False,
) -> AsyncIterator[bool]:
    """Serialize per-seller marketplace work with a PostgreSQL advisory lock.

    A transaction-scoped claim stays on the caller's own session by design:
    its unlock is the commit/rollback of the local operation it guards (see
    create_supply_from_orders), so it must live and die with that
    transaction.

    A session-scoped claim is held on a private connection instead (WMS-435).
    The caller's session is used only to find its engine (`session.bind`) and
    is never read from or written to here, so whatever the caller does with
    it inside the block — commit, rollback, flush, raise — cannot strand the
    lock on a connection that then goes back into the pool still holding it.
    The lock is always released on the very connection that took it, right
    before that connection is closed, regardless of how the block exits.
    """
    if transaction_scoped:
        lock_key = await acquire_marketplace_seller_lock(
            session,
            seller_id,
            marketplace,
            wait_timeout_sec=wait_timeout_sec,
            release_connection_while_waiting=release_connection_while_waiting,
            transaction_scoped=True,
        )
        yield lock_key is not None
        return

    bind = session.bind
    if bind is None or bind.dialect.name != "postgresql":
        # Not on PostgreSQL (SQLite in tests): unchanged behaviour, the lock
        # is always considered taken. No private connection is needed, and
        # checking dialect this way never checks out the caller's session.
        yield True
        return

    async with AsyncSession(bind=bind) as lock_session:
        lock_key = await acquire_marketplace_seller_lock(
            lock_session,
            seller_id,
            marketplace,
            wait_timeout_sec=wait_timeout_sec,
            # Between failed poll attempts the lock's own connection is
            # always handed back to the pool: it does nothing else while
            # sleeping, so there is never a reason to keep it checked out
            # (WMS-435, R4г) — independent of what the caller asked for.
            release_connection_while_waiting=True,
            transaction_scoped=False,
        )
        try:
            yield lock_key is not None
        finally:
            if lock_key is not None:
                try:
                    await release_marketplace_seller_lock(lock_session, lock_key)
                except Exception:
                    # The block's own exception (if any) must reach the
                    # caller unchanged (R2) — never replace or hide it with
                    # an unlock failure. A connection that failed to unlock
                    # must not go back to the pool alive.
                    logger.exception(
                        "marketplace seller lock unlock failed; invalidating "
                        "the lock connection instead of returning it to the pool",
                        extra={"seller_id": str(seller_id), "marketplace": marketplace},
                    )
                    try:
                        await lock_session.invalidate()
                    except Exception:
                        logger.exception(
                            "marketplace seller lock connection invalidation failed",
                            extra={"seller_id": str(seller_id), "marketplace": marketplace},
                        )
