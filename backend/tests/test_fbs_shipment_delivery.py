"""FBS delivery preflight and safe deliver — TC-19, TC-20, TC-21."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import (
    FBS_ORDER_STATUS_CANCELLED,
    FBS_ORDER_STATUS_IN_DELIVERY,
    FbsOrder,
)
from app.models.fbs_supply import FBS_SUPPLY_STATUS_IN_DELIVERY, FBS_SUPPLY_STATUS_PACKED, FbsSupply
from app.models.fbs_wb_operation import (
    WB_OPERATION_STATE_CONFIRMED,
    WB_OPERATION_STATE_PENDING_CONFIRMATION,
    FbsWbOperation,
)
from app.services.wildberries_client import WildberriesClientError
from tests.test_fbs_shipment_pvz import _create_cargo_places, _default_boxes, _prepare_pvz_supply
from tests.test_fbs_shipment_warehouse_sc import (
    _deliver_with_preflight,
    _delivery_preflight,
    _prepare_supply_with_orders,
    _register_ff_admin,
    _setup_seller_with_token,
)


@pytest.fixture
def enable_wb_marketplace_supplies_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)


# TC-19 — fresh sync checklist + stale preflight rejected
@pytest.mark.asyncio
async def test_tc19_delivery_preflight_checklist_and_stale_version(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )

    supply, order_ids = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[980001, 980002],
        supply_name="TC-19 checklist",
    )

    preflight = await _delivery_preflight(async_client, headers, supply["id"])
    assert preflight["can_deliver"] is True
    assert preflight["version"]
    assert preflight["checked_at"]
    check_codes = {check["code"] for check in preflight["checks"]}
    assert "supply_packed" in check_codes
    assert "order_packed" in check_codes

    stale_version = preflight["version"]
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_ids[0])
        assert order is not None
        order.status = FBS_ORDER_STATUS_CANCELLED
        await session.commit()

    stale = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/deliver",
        headers=headers,
        json={
            "idempotency_key": str(uuid.uuid4()),
            "confirmed_preflight_version": stale_version,
        },
    )
    assert stale.status_code == 409
    stale_detail = stale.json()["detail"]
    if isinstance(stale_detail, dict):
        assert stale_detail["code"] == "stale_preflight"
    else:
        assert stale_detail == "stale_preflight"

    refreshed = await _delivery_preflight(async_client, headers, supply["id"])
    assert refreshed["can_deliver"] is False
    assert any(
        check["code"] == "order_cancelled" and not check["ok"]
        for check in refreshed["checks"]
    )


# TC-20 — PVZ deliver with cargo QR; timeout → pending_confirmation; retry idempotent
@pytest.mark.asyncio
async def test_tc20_pvz_deliver_timeout_pending_confirmation(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )

    supply, order_ids = await _prepare_pvz_supply(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[981001, 981002],
        supply_name="TC-20 PVZ deliver",
    )

    create = await _create_cargo_places(
        async_client,
        headers,
        supply["id"],
        count=1,
        boxes=_default_boxes(1),
    )
    assert create.status_code == 201, create.text

    preflight = await _delivery_preflight(async_client, headers, supply["id"])
    assert preflight["can_deliver"] is True
    assert any(
        check["code"] == "cargo_places_ready" and check["ok"]
        for check in preflight["checks"]
    )

    deliver_calls = {"count": 0}

    async def timeout_then_ok(
        client: object,
        *,
        api_token: str,
        supply_id: str,
        marketplace_api_base: str | None = None,
    ) -> None:
        deliver_calls["count"] += 1
        if deliver_calls["count"] == 1:
            raise WildberriesClientError("transport_error")
        from app.services.wildberries_client import deliver_marketplace_supply as real_deliver

        await real_deliver(
            client,  # type: ignore[arg-type]
            api_token=api_token,
            supply_id=supply_id,
            marketplace_api_base=marketplace_api_base,
        )

    monkeypatch.setattr(
        "app.services.fbs_shipment_service.deliver_marketplace_supply",
        timeout_then_ok,
    )

    idem_key = str(uuid.uuid4())
    first = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/deliver",
        headers=headers,
        json={
            "idempotency_key": idem_key,
            "confirmed_preflight_version": preflight["version"],
        },
    )
    assert first.status_code == 504, first.text
    detail = first.json()["detail"]
    assert detail["code"] == "wb_timeout"
    assert detail["retryable"] is True

    async with SessionLocal() as session:
        supply_row = await session.get(FbsSupply, uuid.UUID(supply["id"]))
        assert supply_row is not None
        assert supply_row.status == FBS_SUPPLY_STATUS_PACKED
        assert supply_row.delivered_at is None
        op = await session.scalar(
            select(FbsWbOperation).where(FbsWbOperation.idempotency_key == idem_key)
        )
        assert op is not None
        assert op.state == WB_OPERATION_STATE_PENDING_CONFIRMATION

    retry_preflight = await _delivery_preflight(async_client, headers, supply["id"])
    retry = await async_client.post(
        f"/operations/fbs-supplies/{supply['id']}/deliver",
        headers=headers,
        json={
            "idempotency_key": idem_key,
            "confirmed_preflight_version": retry_preflight["version"],
        },
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["supply"]["status"] == FBS_SUPPLY_STATUS_IN_DELIVERY
    assert deliver_calls["count"] == 2

    async with SessionLocal() as session:
        op = await session.scalar(
            select(FbsWbOperation).where(FbsWbOperation.idempotency_key == idem_key)
        )
        assert op is not None
        assert op.state == WB_OPERATION_STATE_CONFIRMED
        for local_order_id in order_ids:
            order = await session.get(FbsOrder, local_order_id)
            assert order is not None
            assert order.status == FBS_ORDER_STATUS_IN_DELIVERY


# TC-21 — warehouse/sc: no trbx required; supply QR after success; PVZ route differs
@pytest.mark.asyncio
async def test_tc21_warehouse_sc_qr_after_deliver_route_diff(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )

    wh_supply, _ = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[982001],
        supply_name="TC-21 warehouse",
        delivery_type="warehouse_sc",
    )

    wh_preflight = await _delivery_preflight(async_client, headers, wh_supply["id"])
    wh_codes = {check["code"] for check in wh_preflight["checks"]}
    assert "cargo_places_required" not in wh_codes
    assert "cargo_place_qr_not_ready" not in wh_codes
    assert wh_preflight["can_deliver"] is True

    deliver = await _deliver_with_preflight(async_client, headers, wh_supply["id"])
    assert deliver.status_code == 200, deliver.text
    assert deliver.json()["supply"]["status"] == FBS_SUPPLY_STATUS_IN_DELIVERY

    barcode = await async_client.get(
        f"/operations/fbs-supplies/{wh_supply['id']}/barcode",
        headers=headers,
    )
    assert barcode.status_code == 200, barcode.text
    assert barcode.headers["content-type"].startswith("image/png")
    assert len(barcode.content) > 0

    pvz_supply, _ = await _prepare_pvz_supply(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[982002],
        supply_name="TC-21 PVZ route",
    )
    pvz_barcode = await async_client.get(
        f"/operations/fbs-supplies/{pvz_supply['id']}/barcode",
        headers=headers,
    )
    assert pvz_barcode.status_code == 409
    assert pvz_barcode.json()["detail"]["code"] == "wrong_delivery_type"
    pvz_preflight = await _delivery_preflight(async_client, headers, pvz_supply["id"])
    assert pvz_preflight["can_deliver"] is False
    assert any(
        check["code"] == "cargo_places_required" and not check["ok"]
        for check in pvz_preflight["checks"]
    )
