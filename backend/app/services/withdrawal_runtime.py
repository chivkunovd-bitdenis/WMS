"""Trusted server runtime; test transports are injected, never chosen by a request."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from redis.asyncio import Redis

from app.core.settings import settings
from app.db.withdrawal_repository import WithdrawalError
from app.services.true_api_withdrawal import (
    Environment,
    RedisParticipantLimiter,
    TrueApiConfig,
    TrueApiWithdrawalClient,
)
from app.services.withdrawal_traceability import SNAPSHOT_VERSION, traceability_mode


@dataclass(frozen=True)
class WithdrawalRuntime:
    config: TrueApiConfig
    client_factory: Callable[[str], TrueApiWithdrawalClient]
    traceability_metadata_version = SNAPSHOT_VERSION

    def traceability_mode(self, pg: str | None) -> str | None:
        return traceability_mode(pg)

    @property
    def enabled(self) -> bool:
        return (
            self.config.environment != Environment.PRODUCTION
            or self.config.production_submit_enabled
        )

    def client(self, participant_inn: str, environment: str) -> TrueApiWithdrawalClient:
        if environment != self.config.environment:
            raise WithdrawalError("withdrawal_environment_mismatch")
        return self.client_factory(participant_inn)


@asynccontextmanager
async def withdrawal_runtime() -> AsyncIterator[WithdrawalRuntime]:
    config = TrueApiConfig(
        Environment(settings.withdrawal_environment),
        production_submit_enabled=settings.withdrawal_production_submit_enabled,
    )
    broker = settings.celery_broker_url
    if not broker or not broker.startswith(("redis://", "rediss://")):

        def unavailable(inn: str) -> TrueApiWithdrawalClient:
            raise WithdrawalError("withdrawal_shared_limiter_not_configured", 503)

        yield WithdrawalRuntime(config, unavailable)
        return
    async with Redis.from_url(broker, decode_responses=True) as redis, httpx.AsyncClient() as http:
        limiter = RedisParticipantLimiter(redis)
        yield WithdrawalRuntime(
            config,
            lambda inn: TrueApiWithdrawalClient(
                http,
                config,
                limiter,
                inn,
            ),
        )


async def get_withdrawal_runtime() -> AsyncIterator[WithdrawalRuntime]:
    async with withdrawal_runtime() as runtime:
        yield runtime
