"""Real local-DB coverage for the S-32 Ozon account service."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.marketplace_account import MarketplaceAccount
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.user import User
from app.services.marketplace_account_service import MarketplaceAccountService
from app.services.ozon_client import OzonProviderError, validate_seller_info


@dataclass
class RecordedCall:
    host: str
    method: str
    path: str
    body: object
    follow_redirects: bool


class RejectingOzonTransport:
    """Local fake: it permits only the one read-only Call 74 request."""

    def __init__(self, *, status_code: int = 204, error: Exception | None = None) -> None:
        self.status_code = status_code
        self.error = error
        self.calls: list[RecordedCall] = []

    async def request(
        self,
        *,
        host: str,
        method: str,
        path: str,
        headers: dict[str, str],
        json: object,
        follow_redirects: bool,
    ) -> int:
        assert host == "https://api-seller.ozon.ru"
        assert method == "POST"
        assert path == "/v1/seller/info"
        assert json == {}
        assert follow_redirects is False
        assert set(headers) >= {"Client-Id", "Api-Key"}
        self.calls.append(RecordedCall(host, method, path, json, follow_redirects))
        if self.error is not None:
            raise self.error
        return self.status_code


async def _create_scope(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    suffix = uuid.uuid4().hex
    tenant = Tenant(name="Ozon service test", slug=f"ozon-service-{suffix}")
    session.add(tenant)
    await session.flush()
    seller = Seller(tenant_id=tenant.id, name="Ozon seller")
    session.add(seller)
    await session.flush()
    actor = User(
        tenant_id=tenant.id,
        seller_id=seller.id,
        email=f"ozon-service-{suffix}@example.com",
        password_hash="test-only-password-hash",
        role="fulfillment_seller",
    )
    session.add(actor)
    await session.commit()
    return tenant.id, seller.id, actor.id


async def _account_row(
    session: AsyncSession, tenant_id: uuid.UUID, seller_id: uuid.UUID
) -> MarketplaceAccount | None:
    return (
        await session.execute(
            select(MarketplaceAccount).where(
                MarketplaceAccount.tenant_id == tenant_id,
                MarketplaceAccount.seller_id == seller_id,
                MarketplaceAccount.marketplace == "ozon",
                MarketplaceAccount.account_slot == "primary",
            )
        )
    ).scalar_one_or_none()


@pytest.mark.asyncio
async def test_tc_s32_ozon_009_adapter_allows_only_one_read_only_empty_post() -> None:
    transport = RejectingOzonTransport()

    result = await validate_seller_info(
        transport=transport,
        client_id="test-client-handle",
        api_key="test-api-key-handle",
    )

    assert result.status_code == 204
    assert len(transport.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [401, 403, 429, 500, 502, 418])
async def test_tc_s32_ozon_004_adapter_preserves_provider_failure_class(
    status_code: int,
) -> None:
    transport = RejectingOzonTransport(status_code=status_code)

    with pytest.raises(OzonProviderError) as raised:
        await validate_seller_info(
            transport=transport,
            client_id="test-client-handle",
            api_key="test-api-key-handle",
        )

    assert raised.value.status_code == status_code
    assert len(transport.calls) == 1


@pytest.mark.asyncio
async def test_tc_s32_ozon_005_real_db_equal_replay_keeps_one_primary(
    async_client: object,
) -> None:
    """SQLite executes real sessions here; it does not prove PostgreSQL lock semantics."""
    _ = async_client
    async with SessionLocal() as setup_session:
        tenant_id, seller_id, actor_id = await _create_scope(setup_session)

    async with SessionLocal() as first_session, SessionLocal() as second_session:
        first = MarketplaceAccountService(first_session)
        second = MarketplaceAccountService(second_session)
        saved_first, saved_second = await asyncio.gather(
            first.save_validated_candidate(tenant_id, seller_id, actor_id, "client-a", "key-a"),
            second.save_validated_candidate(tenant_id, seller_id, actor_id, "client-a", "key-a"),
        )

    async with SessionLocal() as verification_session:
        count = await verification_session.scalar(
            select(func.count(MarketplaceAccount.id)).where(
                MarketplaceAccount.tenant_id == tenant_id,
                MarketplaceAccount.seller_id == seller_id,
                MarketplaceAccount.marketplace == "ozon",
                MarketplaceAccount.account_slot == "primary",
            )
        )
        row = await _account_row(verification_session, tenant_id, seller_id)

    assert saved_first.account_id == saved_second.account_id
    assert count == 1
    assert row is not None
    assert row.external_account_id == "client-a"


@pytest.mark.asyncio
async def test_tc_s32_ozon_007_real_db_cross_tenant_scope_is_fail_closed(
    async_client: object,
) -> None:
    _ = async_client
    async with SessionLocal() as session:
        tenant_id, seller_id, actor_id = await _create_scope(session)
        service = MarketplaceAccountService(session)
        await service.save_validated_candidate(tenant_id, seller_id, actor_id, "client-a", "key-a")

        with pytest.raises(service.SellerNotFound):
            await service.public_status(uuid.uuid4(), seller_id)


@pytest.mark.asyncio
async def test_tc_s32_ozon_008_real_db_disconnect_erases_ciphertext_and_public_status_is_safe(
    async_client: object,
) -> None:
    _ = async_client
    async with SessionLocal() as session:
        tenant_id, seller_id, actor_id = await _create_scope(session)
        service = MarketplaceAccountService(session)
        await service.save_validated_candidate(
            tenant_id, seller_id, actor_id, "client-handle", "key-handle"
        )
        row = await _account_row(session, tenant_id, seller_id)
        assert row is not None
        assert row.secret_encrypted is not None
        assert row.secret_encrypted != "key-handle"

        status = await service.public_status(tenant_id, seller_id)
        assert set(status) == {
            "marketplace",
            "connected",
            "validation_status",
            "last_validated_at",
            "last_validation_error",
            "credentials_updated_at",
            "last_synced_at",
            "last_sync_error",
        }
        await service.disconnect(tenant_id, seller_id, actor_id)
        cleared = await _account_row(session, tenant_id, seller_id)

    assert cleared is not None
    assert cleared.secret_encrypted is None
    assert cleared.external_account_id is None
    assert "key-handle" not in str(status)
