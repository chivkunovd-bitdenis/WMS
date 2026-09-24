"""Trusted server runtime; test transports are injected, never chosen by a request."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

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
from app.services.withdrawal_service import INTEGRATION_GATE


@dataclass(frozen=True)
class WithdrawalRuntime:
    config: TrueApiConfig
    client_factory: Callable[[str], TrueApiWithdrawalClient]
    traceability_metadata_version: str | None = None
    traceability_modes: dict[str, str] = field(default_factory=dict)

    def traceability_mode(self, pg: str | None) -> str | None:
        return self.traceability_modes.get(pg or "") if self.traceability_metadata_version else None

    @property
    def enabled(self) -> bool:
        return self.config.browser_auth_profile_verified

    def client(self, participant_inn: str, environment: str) -> TrueApiWithdrawalClient:
        if not self.enabled:
            raise WithdrawalError(INTEGRATION_GATE)
        if environment != self.config.environment:
            raise WithdrawalError("withdrawal_environment_mismatch")
        return self.client_factory(participant_inn)


@asynccontextmanager
async def withdrawal_runtime() -> AsyncIterator[WithdrawalRuntime]:
    config = TrueApiConfig(
        Environment(settings.withdrawal_environment),
        browser_auth_profile_verified=settings.withdrawal_browser_auth_profile_verified,
    )
    if not config.browser_auth_profile_verified:

        def closed(inn: str) -> TrueApiWithdrawalClient:
            raise WithdrawalError(INTEGRATION_GATE)

        yield WithdrawalRuntime(config, closed)
        return
    broker = settings.celery_broker_url
    if not broker or not broker.startswith(("redis://", "rediss://")):
        raise WithdrawalError("withdrawal_shared_limiter_not_configured", 503)
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
            settings.withdrawal_traceability_metadata_version,
            dict(settings.withdrawal_traceability_modes),
        )


async def get_withdrawal_runtime() -> AsyncIterator[WithdrawalRuntime]:
    async with withdrawal_runtime() as runtime:
        yield runtime
