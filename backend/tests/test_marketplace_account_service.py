"""Pre-development contract tests for TC-S32-OZON-005/007/008/009.

These tests intentionally import the Call 74 service contract.  Until the slice is
implemented, collection is expected to fail rather than silently skip coverage.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

import pytest

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
async def test_tc_s32_ozon_005_same_pair_replay_and_concurrent_update_keep_one_primary(
    async_client: object,
) -> None:
    """The future service is injected with the fake; no network can be reached."""
    transport = RejectingOzonTransport()
    service = MarketplaceAccountService.from_test_client(async_client, transport=transport)
    tenant_id, seller_id, actor_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    first, replay = await asyncio.gather(
        service.save_candidate(tenant_id, seller_id, actor_id, "client-a", "key-a"),
        service.save_candidate(tenant_id, seller_id, actor_id, "client-a", "key-a"),
    )

    assert first.account_id == replay.account_id
    assert first.credentials_updated_at == replay.credentials_updated_at
    assert await service.count_primary_accounts(tenant_id, seller_id, "ozon") == 1
    assert len(transport.calls) == 2  # one bounded validation per click, never a retry loop


@pytest.mark.asyncio
async def test_tc_s32_ozon_007_cross_tenant_scope_is_fail_closed(async_client: object) -> None:
    service = MarketplaceAccountService.from_test_client(
        async_client, transport=RejectingOzonTransport()
    )
    tenant_a, tenant_b, seller_a, actor_a = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await service.save_candidate(tenant_a, seller_a, actor_a, "client-a", "key-a")

    with pytest.raises(service.SellerNotFound):
        await service.public_status(tenant_b, seller_a)


@pytest.mark.asyncio
async def test_tc_s32_ozon_008_disconnect_erases_ciphertext_and_public_status_has_no_secrets(
    async_client: object,
) -> None:
    service = MarketplaceAccountService.from_test_client(
        async_client, transport=RejectingOzonTransport()
    )
    tenant_id, seller_id, actor_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await service.save_candidate(tenant_id, seller_id, actor_id, "client-handle", "key-handle")

    status = await service.public_status(tenant_id, seller_id)
    assert set(status) == {
        "marketplace", "connected", "validation_status", "last_validated_at",
        "last_validation_error", "credentials_updated_at", "last_synced_at", "last_sync_error",
    }
    await service.disconnect(tenant_id, seller_id, actor_id)
    assert await service.ciphertext_for_test(tenant_id, seller_id) is None
