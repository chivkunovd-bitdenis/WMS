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
from app.models.product import Product
from app.services.wildberries_client import WildberriesClientError
from tests.test_fbs_shipment_pvz import _prepare_pvz_supply
from tests.test_fbs_shipment_warehouse_sc import (
    _create_and_fill_physical_box,
    _deliver_with_preflight,
    _delivery_preflight,
    _prepare_supply_with_orders,
    _register_ff_admin,
    _setup_seller_with_token,
)


@pytest.fixture
def enable_wb_marketplace_supplies_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)


def _mock_actual_composition(
    monkeypatch: pytest.MonkeyPatch,
    supply_orders: dict[str, list[int]],
) -> None:
    async def fetch_actual_order_ids(
        client: object,
        *,
        api_token: str,
        wb_supply_id: str,
        expected_order_ids: list[int] | None = None,
    ) -> list[int]:
        return list(supply_orders.get(wb_supply_id, ()))

    monkeypatch.setattr(
        "app.services.fbs_supply_composition_service.fetch_wb_supply_order_ids",
        fetch_actual_order_ids,
    )


async def _attach_products(
    tenant_id: uuid.UUID,
    seller_id: str,
    order_ids: list[uuid.UUID],
) -> None:
    async with SessionLocal() as session:
        for index, order_id in enumerate(order_ids):
            product = Product(
                tenant_id=tenant_id,
                seller_id=uuid.UUID(seller_id),
                name=f"Shipment product {order_id}",
                sku_code=f"SHIP-{order_id}-{index}",
            )
            session.add(product)
            await session.flush()
            order = await session.get(FbsOrder, order_id)
            assert order is not None
            order.product_id = product.id
        await session.commit()


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
    await _attach_products(tenant_id, seller_id, order_ids)
    _mock_actual_composition(monkeypatch, {supply["wb_supply_id"]: [980001, 980002]})
    await _create_and_fill_physical_box(async_client, headers, supply["id"], order_ids)

    preflight = await _delivery_preflight(async_client, headers, supply["id"])
    assert preflight["can_deliver"] is True, preflight
    assert preflight["version"]
    assert preflight["checked_at"]
    check_codes = {check["code"] for check in preflight["checks"]}
    assert "supply_packed" not in check_codes
    assert "order_packed" not in check_codes
    assert "negative_stock" in check_codes

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
    assert refreshed["can_deliver"] is True
    assert any(
        check["code"] == "wb_terminal_order_ignored" and not check["ok"]
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
    await _attach_products(tenant_id, seller_id, order_ids)
    _mock_actual_composition(monkeypatch, {supply["wb_supply_id"]: [981001, 981002]})

    await _create_and_fill_physical_box(async_client, headers, supply["id"], order_ids)

    preflight = await _delivery_preflight(async_client, headers, supply["id"])
    assert preflight["can_deliver"] is True, preflight
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

    async def confirmed_on_reconcile(*args: object, **kwargs: object) -> str:
        return WB_OPERATION_STATE_CONFIRMED

    monkeypatch.setattr(
        "app.services.fbs_shipment_service.reconcile_supply_delivered",
        confirmed_on_reconcile,
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
    assert deliver_calls["count"] == 1

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


# TC-21 — warehouse/sc: no trbx required; PVZ requires physical boxes first;
# both routes get a supply QR after a confirmed deliver. WB's supply-barcode
# endpoint (GET /api/v3/supplies/{id}/barcode) was verified live on 2026-08-17
# to return 200 with a PNG for a pvz supply (WB-GI-266096235) exactly like a
# warehouse_sc one (WB-GI-265889432), so the backend no longer gates the
# supply QR on delivery_type — only "must be delivered" still applies.
@pytest.mark.asyncio
async def test_tc21_warehouse_sc_qr_after_deliver_route_diff(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )

    wh_supply, wh_order_ids = await _prepare_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[982001],
        supply_name="TC-21 warehouse",
        delivery_type="warehouse_sc",
    )
    await _attach_products(tenant_id, seller_id, wh_order_ids)
    await _create_and_fill_physical_box(async_client, headers, wh_supply["id"], wh_order_ids)
    actual_composition = {wh_supply["wb_supply_id"]: [982001]}
    _mock_actual_composition(monkeypatch, actual_composition)

    wh_preflight = await _delivery_preflight(async_client, headers, wh_supply["id"])
    wh_codes = {check["code"] for check in wh_preflight["checks"]}
    assert "cargo_places_required" not in wh_codes
    assert "cargo_place_qr_not_ready" not in wh_codes
    assert wh_preflight["can_deliver"] is True, wh_preflight

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

    pvz_supply, pvz_order_ids = await _prepare_pvz_supply(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
        wb_order_ids=[982002],
        supply_name="TC-21 PVZ route",
    )
    await _attach_products(tenant_id, seller_id, pvz_order_ids)
    actual_composition[pvz_supply["wb_supply_id"]] = [982002]

    # Отличие маршрута ПВЗ: у него появляется предупреждение про физические
    # короба, которого нет у склада/СЦ. Запретом оно не является — с 01.09.2026
    # передачу останавливает только уже переданная или пустая поставка.
    pvz_barcode = await async_client.get(
        f"/operations/fbs-supplies/{pvz_supply['id']}/barcode",
        headers=headers,
    )
    assert pvz_barcode.status_code == 409
    assert pvz_barcode.json()["detail"]["code"] == "supply_bad_status"
    pvz_preflight = await _delivery_preflight(async_client, headers, pvz_supply["id"])
    assert pvz_preflight["can_deliver"] is True
    assert any(
        check["code"] == "physical_boxes_required" and check["severity"] == "warning"
        for check in pvz_preflight["checks"]
    )

    # Once PVZ is actually delivered, its supply QR works exactly like warehouse/sc's.
    await _create_and_fill_physical_box(async_client, headers, pvz_supply["id"], pvz_order_ids)
    pvz_deliver = await _deliver_with_preflight(async_client, headers, pvz_supply["id"])
    assert pvz_deliver.status_code == 200, pvz_deliver.text
    assert pvz_deliver.json()["supply"]["status"] == FBS_SUPPLY_STATUS_IN_DELIVERY

    pvz_barcode_after_deliver = await async_client.get(
        f"/operations/fbs-supplies/{pvz_supply['id']}/barcode",
        headers=headers,
    )
    assert pvz_barcode_after_deliver.status_code == 200, pvz_barcode_after_deliver.text
    assert pvz_barcode_after_deliver.headers["content-type"].startswith("image/png")
    assert len(pvz_barcode_after_deliver.content) > 0
