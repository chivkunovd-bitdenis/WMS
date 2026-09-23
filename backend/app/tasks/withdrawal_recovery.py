"""Explicit read-only sweep entrypoint; not scheduled until integration acceptance."""

from __future__ import annotations

import httpx
from redis.asyncio import Redis

from app.core.settings import settings
from app.db.session import SessionLocal
from app.services.true_api_withdrawal import (
    RedisParticipantLimiter,
    TrueApiConfig,
    TrueApiWithdrawalClient,
)
from app.services.withdrawal_recovery import claim_work, purge_expired_tokens, recover_one


async def run_withdrawal_recovery(*, batch_size: int = 100) -> int:
    """Recover persisted due work after restarts; no process-local queue or retries.

    The scheduler registration is intentionally a release gate. The production
    adapter uses the existing shared Redis broker and fails closed without it.
    """
    if not 1 <= batch_size <= 1000:
        raise ValueError("invalid_withdrawal_batch_size")
    async with SessionLocal() as session:
        await purge_expired_tokens(session)
    broker = settings.celery_broker_url
    if not broker or not broker.startswith(("redis://", "rediss://")):
        raise RuntimeError("withdrawal_shared_limiter_not_configured")
    processed = 0
    async with Redis.from_url(broker, decode_responses=True) as redis:
        limiter = RedisParticipantLimiter(redis)
        async with httpx.AsyncClient() as http:
            for _ in range(batch_size):
                async with SessionLocal() as session:
                    work = await claim_work(session)
                if work is None:
                    break
                client = TrueApiWithdrawalClient(
                    http,
                    TrueApiConfig(work.environment),
                    limiter,
                    work.participant_inn,
                )
                await recover_one(SessionLocal, work, client)
                processed += 1
    return processed
