"""FBS post-delivery tracking and partial acceptance — TC-22."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import (
    FBS_ORDER_STATUS_DEFECT,
    FBS_ORDER_STATUS_IN_DELIVERY,
    FBS_ORDER_STATUS_SORTED,
    FbsOrder,
)
from app.models.fbs_supply import (
    FBS_SUPPLY_STATUS_ASSEMBLING,
    FBS_SUPPLY_STATUS_DONE,
    FBS_SUPPLY_STATUS_IN_DELIVERY,
    FbsSupply,
)
from app.services.fbs_tracking_service import (
    TRACKING_STATUS_PARTIALLY_REJECTED,
    build_partial_rejection_summary,
    compute_supply_tracking_state,
    sync_in_delivery_supplies,
    sync_supply_tracking,
)
from app.services.wb_marketplace_orders_service import upsert_order_from_wb_row
from app.services.wildberries_client import WildberriesClientError
from app.services.wildberries_fbs_client import MarketplaceSupplyDetails
from tests.fbs_seed_helpers import seed_fbs_warehouse_binding
from tests.test_fbs_shipment_warehouse_sc import (
    _register_ff_admin,
    _setup_seller_with_token,
    _wb_order_row,
)


async def _seed_in_delivery_supply(
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    wb_order_ids: list[int],
    supply_status: str = FBS_SUPPLY_STATUS_IN_DELIVERY,
) -> uuid.UUID:
    supply_id = uuid.uuid4()
    async with SessionLocal() as session:
        await seed_fbs_warehouse_binding(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            wms_warehouse_id=warehouse_id,
        )
        supply = FbsSupply(
            id=supply_id,
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            wb_supply_id=f"WB-SUP-{supply_id.hex[:8]}",
            name="TC-22 tracking supply",
            status=supply_status,
            delivery_type="warehouse_sc",
            delivered_at=(
                datetime.now(tz=UTC)
                if supply_status == FBS_SUPPLY_STATUS_IN_DELIVERY
                else None
            ),
        )
        session.add(supply)
        for wb_order_id in wb_order_ids:
            order, _ = await upsert_order_from_wb_row(
                session,
                tenant_id,
                seller_id,
                _wb_order_row(order_id=wb_order_id),
            )
            order.supply_id = supply_id
            order.status = FBS_ORDER_STATUS_IN_DELIVERY
            order.wb_status = "waiting"
            order.warehouse_id = warehouse_id
        await session.commit()
    return supply_id


def _status_map(*pairs: tuple[int, str]) -> dict[int, str]:
    return {order_id: status for order_id, status in pairs}


def _patch_supply_details(
    monkeypatch: pytest.MonkeyPatch,
    *,
    done: bool = False,
    error: WildberriesClientError | None = None,
) -> None:
    async def _mock_details(
        _client: httpx.AsyncClient,
        *,
        api_token: str,
        supply_id: str,
        marketplace_api_base: str | None = None,
    ) -> MarketplaceSupplyDetails:
        _ = api_token, marketplace_api_base
        if error is not None:
            raise error
        return MarketplaceSupplyDetails(
            supply_id=supply_id,
            name="tracking supply",
            done=done,
        )

    monkeypatch.setattr(
        "app.services.fbs_tracking_service.fetch_marketplace_supply_details",
        _mock_details,
    )


# TC-22 — mixed accepted/rejected preserved; repeated sync idempotent
@pytest.mark.asyncio
async def test_tc22_partial_acceptance_mixed_orders_preserved(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = async_client
    tenant_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    warehouse_id = uuid.uuid4()
    supply_id = await _seed_in_delivery_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        wb_order_ids=[990001, 990002, 990003],
    )

    statuses = _status_map(
        (990001, "sorted"),
        (990002, "defect"),
        (990003, "waiting"),
    )

    async def _mock_status(
        _client: httpx.AsyncClient,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[dict[str, Any]]:
        _ = api_token, marketplace_api_base
        return [
            {"id": oid, "supplierStatus": statuses[oid], "wbStatus": statuses[oid]}
            for oid in order_ids
            if oid in statuses
        ]

    async def _token(*_args: object, **_kwargs: object) -> str:
        return "token"

    monkeypatch.setattr(
        "app.services.fbs_tracking_service.fetch_marketplace_orders_status",
        _mock_status,
    )
    monkeypatch.setattr(
        "app.services.fbs_tracking_service._resolve_marketplace_api_token",
        _token,
    )
    _patch_supply_details(monkeypatch)

    async with SessionLocal() as session, httpx.AsyncClient() as http_client:
        first = await sync_supply_tracking(
            session, tenant_id, supply_id, http_client
        )
        await session.commit()
        second = await sync_supply_tracking(
            session, tenant_id, supply_id, http_client
        )
        await session.commit()

    assert first.orders_updated == 3
    assert second.orders_updated == 3

    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        assert supply is not None
        assert supply.last_wb_sync_at is not None
        orders = list(
            (
                await session.execute(
                    select(FbsOrder).where(FbsOrder.supply_id == supply_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(orders) == 3
        by_wb = {int(o.wb_order_id): o for o in orders}
        assert by_wb[990001].status == FBS_ORDER_STATUS_SORTED
        assert by_wb[990001].wb_status == "sorted"
        assert by_wb[990002].status == FBS_ORDER_STATUS_DEFECT
        assert by_wb[990002].wb_status == "defect"
        assert by_wb[990003].status == FBS_ORDER_STATUS_IN_DELIVERY
        assert by_wb[990003].wb_status == "waiting"

        state = compute_supply_tracking_state(supply, orders)
        assert state == TRACKING_STATUS_PARTIALLY_REJECTED

        summary = build_partial_rejection_summary(orders)
        assert len(summary["accepted_orders"]) == 2
        assert len(summary["rejected_orders"]) == 1
        rejected = summary["rejected_orders"][0]
        assert rejected["wb_order_id"] == 990002
        assert rejected["reason"]
        assert rejected["remaining_deadline"]


@pytest.mark.asyncio
async def test_tc22_sync_tracking_api_updates_workspace(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    supply_id = await _seed_in_delivery_supply(
        tenant_id=tenant_id,
        seller_id=uuid.UUID(seller_id),
        warehouse_id=uuid.UUID(warehouse_id),
        wb_order_ids=[991001, 991002],
    )

    statuses = _status_map((991001, "sold"), (991002, "waiting"))

    async def _mock_status(
        _client: httpx.AsyncClient,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[dict[str, Any]]:
        _ = api_token, marketplace_api_base
        return [
            {"id": oid, "supplierStatus": statuses[oid], "wbStatus": statuses[oid]}
            for oid in order_ids
            if oid in statuses
        ]

    monkeypatch.setattr(
        "app.services.fbs_tracking_service.fetch_marketplace_orders_status",
        _mock_status,
    )

    resp = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/sync-tracking",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["stage"] == "tracking"
    assert payload["tracking_summary"] is not None
    assert payload["tracking_summary"]["status"] == TRACKING_STATUS_PARTIALLY_REJECTED
    assert payload["partial_rejection"] is not None
    assert len(payload["partial_rejection"]["accepted_orders"]) == 2
    assert payload["last_wb_sync_at"] is not None
    assert payload["wb_sync_stale"] is False

    labels = {item["tracking_label"] for item in payload["tracking_summary"]["orders"]}
    assert "done" in labels
    assert "accepted" in labels


@pytest.mark.asyncio
async def test_tc22_autopoll_sync_in_delivery_supplies_per_seller(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = async_client
    tenant_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    warehouse_id = uuid.uuid4()
    supply_id = await _seed_in_delivery_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        wb_order_ids=[992001],
    )

    async def _mock_status(
        _client: httpx.AsyncClient,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[dict[str, Any]]:
        _ = api_token, marketplace_api_base
        return [{"id": oid, "supplierStatus": "sorted", "wbStatus": "sorted"} for oid in order_ids]

    async def _token(*_args: object, **_kwargs: object) -> str:
        return "token"

    monkeypatch.setattr(
        "app.services.fbs_tracking_service.fetch_marketplace_orders_status",
        _mock_status,
    )
    monkeypatch.setattr(
        "app.services.fbs_tracking_service._resolve_marketplace_api_token",
        _token,
    )
    _patch_supply_details(monkeypatch)

    async with SessionLocal() as session, httpx.AsyncClient() as http_client:
        result = await sync_in_delivery_supplies(
            session, tenant_id, seller_id, http_client
        )
        await session.commit()

    assert result.supplies_synced == 1
    assert result.orders_updated == 1

    async with SessionLocal() as session:
        order = (
            await session.execute(
                select(FbsOrder).where(FbsOrder.supply_id == supply_id)
            )
        ).scalar_one()
        assert order.status == FBS_ORDER_STATUS_SORTED
        supply = await session.get(FbsSupply, supply_id)
        assert supply is not None
        assert supply.last_wb_sync_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("wb_done", "expected_status"),
    [
        (True, FBS_SUPPLY_STATUS_DONE),
        (False, FBS_SUPPLY_STATUS_ASSEMBLING),
    ],
)
async def test_wb_done_is_authoritative_for_assembling_supply(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    wb_done: bool,
    expected_status: str,
) -> None:
    _ = async_client
    tenant_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    warehouse_id = uuid.uuid4()
    supply_id = await _seed_in_delivery_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        wb_order_ids=[994001],
        supply_status=FBS_SUPPLY_STATUS_ASSEMBLING,
    )

    order_status_calls = 0

    async def _mock_status(
        _client: httpx.AsyncClient,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[dict[str, Any]]:
        nonlocal order_status_calls
        order_status_calls += 1
        _ = api_token, marketplace_api_base
        return [
            {"id": order_id, "supplierStatus": "confirm", "wbStatus": "waiting"}
            for order_id in order_ids
        ]

    async def _token(*_args: object, **_kwargs: object) -> str:
        return "token"

    monkeypatch.setattr(
        "app.services.fbs_tracking_service.fetch_marketplace_orders_status",
        _mock_status,
    )
    monkeypatch.setattr(
        "app.services.fbs_tracking_service._resolve_marketplace_api_token",
        _token,
    )
    _patch_supply_details(monkeypatch, done=wb_done)

    async with SessionLocal() as session, httpx.AsyncClient() as http_client:
        result = await sync_in_delivery_supplies(
            session, tenant_id, seller_id, http_client
        )
        await session.commit()

    assert result.supplies_synced == 1
    assert result.orders_updated == 0
    assert order_status_calls == 0
    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        assert supply is not None
        assert supply.status == expected_status


@pytest.mark.asyncio
async def test_supply_details_error_keeps_order_sync_working(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = async_client
    tenant_id = uuid.uuid4()
    seller_id = uuid.uuid4()
    warehouse_id = uuid.uuid4()
    supply_id = await _seed_in_delivery_supply(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        wb_order_ids=[995001],
        supply_status=FBS_SUPPLY_STATUS_IN_DELIVERY,
    )

    async def _mock_status(
        _client: httpx.AsyncClient,
        *,
        api_token: str,
        order_ids: list[int],
        marketplace_api_base: str | None = None,
    ) -> list[dict[str, Any]]:
        _ = api_token, marketplace_api_base
        return [
            {"id": order_id, "supplierStatus": "confirm", "wbStatus": "waiting"}
            for order_id in order_ids
        ]

    async def _token(*_args: object, **_kwargs: object) -> str:
        return "token"

    monkeypatch.setattr(
        "app.services.fbs_tracking_service.fetch_marketplace_orders_status",
        _mock_status,
    )
    monkeypatch.setattr(
        "app.services.fbs_tracking_service._resolve_marketplace_api_token",
        _token,
    )
    _patch_supply_details(
        monkeypatch,
        error=WildberriesClientError("transport_error"),
    )

    async with SessionLocal() as session, httpx.AsyncClient() as http_client:
        result = await sync_in_delivery_supplies(
            session, tenant_id, seller_id, http_client
        )
        await session.commit()

    assert result.supplies_synced == 1
    assert result.orders_updated == 1
    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        assert supply is not None
        assert supply.status == FBS_SUPPLY_STATUS_IN_DELIVERY
        assert supply.last_wb_sync_at is not None


@pytest.mark.asyncio
async def test_tc22_stale_sync_warning_when_last_sync_old(
    async_client: AsyncClient,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    supply_id = await _seed_in_delivery_supply(
        tenant_id=tenant_id,
        seller_id=uuid.UUID(seller_id),
        warehouse_id=uuid.UUID(warehouse_id),
        wb_order_ids=[993001],
    )
    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        assert supply is not None
        supply.last_wb_sync_at = datetime.now(tz=UTC) - timedelta(hours=2)
        await session.commit()

    resp = await async_client.get(
        f"/operations/fbs-supplies/{supply_id}/workspace",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["wb_sync_stale"] is True
