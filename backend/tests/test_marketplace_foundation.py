from __future__ import annotations

import uuid

import pytest

from app.models.fbs_order import FbsOrder
from app.models.fbs_supply import FbsSupply
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.marketplace_unload import MarketplaceUnloadRequest
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.services.marketplace_provider import (
    FakeMarketplaceTransport,
    MarketplaceBackoff,
    MarketplaceProviderError,
    OzonMarketplaceProvider,
    provider_error_message,
)
from app.services.marketplace_seller_lock_service import marketplace_seller_lock_key


@pytest.mark.asyncio
async def test_autopoll_failure_is_isolated_by_seller_and_marketplace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import fbs_autopoll_service as autopoll

    seller_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    targets = [
        autopoll.SellerPollTarget(tenant_id, seller_id, "ozon"),
        autopoll.SellerPollTarget(tenant_id, seller_id, "wb"),
    ]
    calls: list[str] = []

    async def fake_targets(session: object) -> list[autopoll.SellerPollTarget]:
        _ = session
        return targets

    async def fake_poll(
        session: object,
        target: autopoll.SellerPollTarget,
        http_client: object,
        *,
        include_history: bool = False,
    ) -> dict[str, int]:
        _ = session, http_client, include_history
        calls.append(target.marketplace)
        if target.marketplace == "ozon":
            raise MarketplaceProviderError("ozon", 403, {"code": 7})
        return {
            "orders_upserted": 1,
            "orders_created": 1,
            "statuses_updated": 0,
            "stocks_bindings_processed": 0,
            "stock_errors": 0,
        }

    monkeypatch.setattr(autopoll, "list_marketplace_poll_targets", fake_targets)
    monkeypatch.setattr(autopoll, "poll_marketplace_orders_for_target", fake_poll)

    result = await autopoll.poll_fbs_orders_all_sellers()

    assert calls == ["ozon", "wb"]
    assert result.sellers_polled == 1
    assert result.seller_errors == 1
    assert result.orders_created == 1
    assert result.marketplace_breakdown["ozon"]["errors"] == 1
    assert result.marketplace_breakdown["wb"]["successful_pairs"] == 1
    assert result.marketplace_breakdown["wb"]["orders_created"] == 1


@pytest.mark.asyncio
async def test_autopoll_429_backoff_skips_only_limited_marketplace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import fbs_autopoll_service as autopoll

    seller_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    targets = [
        autopoll.SellerPollTarget(tenant_id, seller_id, "ozon"),
        autopoll.SellerPollTarget(tenant_id, seller_id, "wb"),
    ]
    calls: list[str] = []

    async def fake_targets(session: object) -> list[autopoll.SellerPollTarget]:
        _ = session
        return targets

    async def fake_poll(
        session: object,
        target: autopoll.SellerPollTarget,
        http_client: object,
        *,
        include_history: bool = False,
    ) -> dict[str, int]:
        _ = session, http_client, include_history
        calls.append(target.marketplace)
        if target.marketplace == "ozon":
            raise MarketplaceProviderError(
                "ozon",
                429,
                {"retry_after_seconds": 30},
            )
        return {
            "orders_upserted": 0,
            "orders_created": 0,
            "statuses_updated": 0,
            "stocks_bindings_processed": 0,
            "stock_errors": 0,
        }

    monkeypatch.setattr(autopoll, "_MARKETPLACE_BACKOFF", MarketplaceBackoff())
    monkeypatch.setattr(autopoll, "list_marketplace_poll_targets", fake_targets)
    monkeypatch.setattr(autopoll, "poll_marketplace_orders_for_target", fake_poll)

    first = await autopoll.poll_fbs_orders_all_sellers()
    second = await autopoll.poll_fbs_orders_all_sellers()

    assert calls == ["ozon", "wb", "wb"]
    assert first.marketplace_breakdown["ozon"]["errors"] == 1
    assert second.marketplace_breakdown["ozon"]["backoff_skips"] == 1
    assert second.marketplace_breakdown["wb"]["successful_pairs"] == 1


@pytest.mark.asyncio
async def test_movement_publish_attempts_each_marketplace_independently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import fbs_autopoll_service as autopoll
    from app.services import fbs_stock_publish_service as stock_publish

    seller_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    targets = [
        autopoll.SellerPollTarget(tenant_id, seller_id, "ozon"),
        autopoll.SellerPollTarget(tenant_id, seller_id, "wb"),
    ]
    calls: list[str] = []

    async def fake_targets(session: object) -> list[autopoll.SellerPollTarget]:
        _ = session
        return targets

    async def fake_sync(
        session: object,
        target: autopoll.SellerPollTarget,
        http_client: object,
    ) -> autopoll.SellerStockSyncResult:
        _ = session, http_client
        calls.append(target.marketplace)
        if target.marketplace == "ozon":
            raise MarketplaceProviderError("ozon", 503)
        return autopoll.SellerStockSyncResult(bindings_processed=1, products_confirmed=1)

    monkeypatch.setattr(autopoll, "list_marketplace_poll_targets", fake_targets)
    monkeypatch.setattr(autopoll, "sync_marketplace_stocks_for_target", fake_sync)

    await stock_publish.publish_seller_stocks_now(tenant_id, seller_id)

    assert calls == ["ozon", "wb"]


@pytest.mark.parametrize(
    "model",
    [FbsOrder, FbsSupply, FbsWarehouseBinding, MarketplaceUnloadRequest],
)
def test_marketplace_entities_keep_wb_as_backward_compatible_default(model: type[object]) -> None:
    marketplace = model.__table__.columns["marketplace"]

    assert marketplace.nullable is False
    assert marketplace.default.arg == "wb"
    assert marketplace.server_default.arg == "wb"


def test_product_marketplace_link_is_generic_and_multi_provider() -> None:
    columns = ProductMarketplaceLink.__table__.columns

    expected = {
        "product_id",
        "seller_id",
        "marketplace",
        "external_product_id",
        "external_offer_id",
    }
    assert expected <= set(columns.keys())
    assert "ozon" not in ProductMarketplaceLink.__tablename__
    constraint_names = {
        constraint.name for constraint in ProductMarketplaceLink.__table__.constraints
    }
    assert "uq_product_marketplace_links_external_sku" in constraint_names


def test_lock_key_is_scoped_by_seller_and_marketplace() -> None:
    seller_id = uuid.uuid4()

    wb_key = marketplace_seller_lock_key(seller_id, "wb")
    ozon_key = marketplace_seller_lock_key(seller_id, "ozon")

    assert wb_key != ozon_key
    assert wb_key == marketplace_seller_lock_key(seller_id, "wb")


def test_backoff_is_independent_for_each_marketplace() -> None:
    backoff = MarketplaceBackoff()

    backoff.record_rate_limit("ozon", retry_after_seconds=30)

    assert backoff.remaining_seconds("ozon", now=backoff.now()) > 0
    assert backoff.remaining_seconds("wb", now=backoff.now()) == 0


@pytest.mark.parametrize(
    ("status_code", "payload", "expected"),
    [
        (403, {"code": 7}, "Кабинет Ozon заблокирован. Обратитесь в поддержку Ozon."),
        (401, {}, "Ozon отклонил данные подключения."),
        (429, {}, "Ozon временно ограничил частоту запросов."),
        (503, {}, "Ozon временно недоступен."),
    ],
)
def test_ozon_errors_have_operator_safe_messages(
    status_code: int,
    payload: dict[str, object],
    expected: str,
) -> None:
    error = MarketplaceProviderError(
        marketplace="ozon",
        status_code=status_code,
        payload=payload,
    )

    assert provider_error_message(error) == expected


@pytest.mark.asyncio
async def test_ozon_provider_uses_injected_fake_transport_only() -> None:
    transport = FakeMarketplaceTransport(
        orders=[{"posting_number": "123-456-1", "status": "awaiting_packaging"}],
    )
    provider = OzonMarketplaceProvider(transport=transport)

    result = await provider.fetch_orders(
        client_id="client-id",
        api_key="api-key",
    )

    assert result == [{"posting_number": "123-456-1", "status": "awaiting_packaging"}]
    assert transport.calls == [("fetch_orders", "client-id")]


@pytest.mark.asyncio
async def test_ozon_order_labels_use_dedicated_fake_transport_contract() -> None:
    transport = FakeMarketplaceTransport(
        order_labels=[{"posting_number": "ozon-posting-1", "file": "png"}],
    )
    provider = OzonMarketplaceProvider(transport=transport)

    rows = await provider.fetch_order_labels(
        client_id="client-id",
        api_key="api-key",
        posting_numbers=["ozon-posting-1"],
    )

    assert rows == [{"posting_number": "ozon-posting-1", "file": "png"}]
    assert transport.calls == [("fetch_order_labels", "client-id")]


@pytest.mark.asyncio
async def test_ozon_blocked_response_stops_remaining_cycle_calls() -> None:
    transport = FakeMarketplaceTransport(
        errors={"fetch_orders": MarketplaceProviderError("ozon", 403, {"code": 7})},
    )
    provider = OzonMarketplaceProvider(transport=transport)

    with pytest.raises(MarketplaceProviderError) as first:
        await provider.fetch_orders(client_id="client-id", api_key="api-key")
    with pytest.raises(MarketplaceProviderError) as second:
        await provider.fetch_statuses(client_id="client-id", api_key="api-key", order_ids=["1"])

    assert first.value.is_account_blocked is True
    assert second.value.is_account_blocked is True
    assert transport.calls == [("fetch_orders", "client-id")]
