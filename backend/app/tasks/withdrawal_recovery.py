"""Registered durable sweeper; production create has a separate release gate."""

from __future__ import annotations

import asyncio

import httpx
from redis.asyncio import Redis
from sqlalchemy import select

from app.celery_app import celery_app
from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.marking_withdrawal import WithdrawalDocument
from app.services.true_api_withdrawal import (
    RedisParticipantLimiter,
    TrueApiConfig,
    TrueApiWithdrawalClient,
)
from app.services.withdrawal_recovery import claim_work, purge_expired_tokens, recover_one
from app.services.withdrawal_runtime import withdrawal_runtime
from app.services.withdrawal_submission import submit_one


async def run_withdrawal_recovery(*, batch_size: int = 100) -> int:
    """Recover persisted due work after restarts; no process-local queue or retries.

    The production adapter uses the shared Redis broker and fails closed without it.
    """
    if not 1 <= batch_size <= 1000:
        raise ValueError("invalid_withdrawal_batch_size")
    async with SessionLocal() as session:
        await purge_expired_tokens(session)
        exists = await session.scalar(
            select(WithdrawalDocument.id)
            .where(
                WithdrawalDocument.state.in_(["submitting", "submitted", "polling", "reconciling"]),
            )
            .limit(1)
        )
        if exists is None:
            return 0
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


async def run_withdrawal_jobs(*, batch_size: int = 100) -> int:
    if not 1 <= batch_size <= 1000:
        raise ValueError("invalid_withdrawal_batch_size")
    submitted = 0
    async with withdrawal_runtime() as runtime:
        for _ in range(batch_size):
            if not await submit_one(SessionLocal, runtime):
                break
            submitted += 1
    return submitted + await run_withdrawal_recovery(batch_size=batch_size)


@celery_app.task(name="wms.withdrawal_poll")
def withdrawal_poll() -> int:
    return asyncio.run(run_withdrawal_jobs())
