"""TC-NEW-FBS-CANCEL-PACK — operation guards for cancelled FBS orders."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from httpx import AsyncClient

from app.core.settings import settings
from app.db.session import SessionLocal
from app.models.fbs_order import FBS_ORDER_STATUS_CANCELLED, FbsOrder
from app.models.fbs_supply import FBS_SUPPLY_STATUS_ASSEMBLING, FbsSupply
from tests.test_fbs_packaging_integration import (
    _create_supply_with_orders,
    _seed_picks_for_supply_orders,
    _setup_seller_with_token,
)
from tests.test_fbs_picking import (
    _create_product,
    _create_seller_and_warehouse,
    _register_ff_admin,
    _seed_pick_supply,
)
from tests.test_fbs_print_assets import _seed_supply_with_orders
from tests.test_fbs_supply_assembly import _register_ff_admin as _register_print_admin


@pytest.fixture
def enable_wb_marketplace_supplies_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "e2e_mock_wb_marketplace_supplies", True)


# TC-NEW-FBS-CANCEL-PACK-003 — one cancelled order does not block the rest of a print batch.
@pytest.mark.asyncio
async def test_cancelled_order_print_is_human_readable_and_batch_remains_partial(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, _ = await _register_print_admin(async_client)
    supply_data, order_ids, _tenant_id = await _seed_supply_with_orders(
        async_client,
        headers,
        order_count=2,
        base_order_id=9_970_001,
    )
    supply_id = uuid.UUID(str(supply_data["id"]))
    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        cancelled = await session.get(FbsOrder, order_ids[0])
        assert supply is not None and cancelled is not None
        cancelled.status = FBS_ORDER_STATUS_CANCELLED
        cancelled.supplier_status = "canceled_by_client"
        cancelled.wb_supply_id = supply.wb_supply_id
        cancelled.supply_id = None
        await session.commit()

    response = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/print-assets",
        headers=headers,
        json={
            "kind": "order_sticker",
            "order_ids": [str(order_id) for order_id in order_ids],
            "retry_missing": False,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["requested"] == 2
    assert body["ready"] == 1
    assert body["failed"] == 1
    assert len(body["assets"]) == 1
    assert body["order_errors"] == [
        {
            "order_id": str(order_ids[0]),
            "wb_order_id": 9_970_001,
            "code": "order_cancelled",
            "message": "Заказ отменён покупателем, клеить стикер нельзя.",
        }
    ]

    tape = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/order-print-tape",
        headers=headers,
        json={
            "order_ids": [str(order_id) for order_id in order_ids],
            "layout_json": {"units": []},
            "allow_partial": True,
            "include_order_qr": True,
            "reprint": False,
        },
    )
    assert tape.status_code == 200, tape.text
    assert tape.json()["requested"] == 2
    assert tape.json()["ready"] == 1
    assert tape.json()["failed"] == 1
    assert [item["order_id"] for item in tape.json()["orders"]] == [str(order_ids[1])]
    assert tape.json()["order_errors"][0]["message"] == (
        "Заказ отменён покупателем, клеить стикер нельзя."
    )

    ready_asset = body["assets"][0]
    async with SessionLocal() as session:
        formerly_ready = await session.get(FbsOrder, order_ids[1])
        assert formerly_ready is not None
        formerly_ready.status = FBS_ORDER_STATUS_CANCELLED
        formerly_ready.supplier_status = "canceled_by_client"
        await session.commit()
    cached_content = await async_client.get(ready_asset["download_url"], headers=headers)
    assert cached_content.status_code == 409, cached_content.text
    assert cached_content.json()["detail"]["message"] == (
        "Заказ отменён покупателем, клеить стикер нельзя."
    )


# TC-NEW-FBS-CANCEL-PACK-004 — a stale pick is rejected after cancellation detaches the order.
@pytest.mark.asyncio
async def test_cancelled_order_cannot_be_picked(
    async_client: AsyncClient,
) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix
    )
    barcode = f"CANCEL-PICK-{suffix[-8:]}"
    product_id = await _create_product(
        async_client,
        headers,
        seller_id,
        sku=f"CANCEL-PICK-{suffix}",
        barcode=barcode,
    )
    supply_id, order_ids, _location_code = await _seed_pick_supply(
        async_client,
        headers,
        tenant_id,
        seller_id,
        warehouse_id,
        location_id,
        product_id,
        stock_qty=1,
        order_specs=[(71, timedelta(hours=4))],
        barcode=barcode,
    )
    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        order = await session.get(FbsOrder, order_ids[0])
        assert supply is not None and order is not None
        order.status = FBS_ORDER_STATUS_CANCELLED
        order.supplier_status = "canceled_by_client"
        order.wb_supply_id = supply.wb_supply_id
        order.supply_id = None
        await session.commit()

    response = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/pick/scan-product",
        headers=headers,
        json={
            "location_id": str(location_id),
            "product_barcode": barcode,
            "order_id": str(order_ids[0]),
            "idempotency_key": "cancelled-pick",
        },
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == {
        "code": "order_cancelled",
        "message": "Заказ отменён покупателем, подбирать нельзя.",
        "context": {"order_id": str(order_ids[0])},
        "retryable": False,
    }


# TC-NEW-FBS-CANCEL-PACK-005 — stale packaging action is rejected before stock conversion.
@pytest.mark.asyncio
async def test_cancelled_order_cannot_be_packed(
    async_client: AsyncClient,
    enable_wb_marketplace_supplies_mock: None,
) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id = await _setup_seller_with_token(async_client, headers, suffix)
    supply_id_raw, order_ids = await _create_supply_with_orders(
        async_client,
        headers,
        seller_id,
        warehouse_id,
        tenant_id,
    )
    supply_id = uuid.UUID(supply_id_raw)
    response = await async_client.put(
        f"/operations/fbs-supplies/{supply_id}/status",
        headers=headers,
        json={"status": FBS_SUPPLY_STATUS_ASSEMBLING},
    )
    assert response.status_code == 200, response.text
    task_id = uuid.UUID(response.json()["packaging_task_id"])
    await _seed_picks_for_supply_orders(tenant_id, supply_id, uuid.UUID(warehouse_id))

    async with SessionLocal() as session:
        supply = await session.get(FbsSupply, supply_id)
        order = await session.get(FbsOrder, order_ids[0])
        assert supply is not None and order is not None
        product_id = order.product_id
        order.status = FBS_ORDER_STATUS_CANCELLED
        order.supplier_status = "canceled_by_client"
        order.wb_supply_id = supply.wb_supply_id
        order.supply_id = None
        await session.commit()
    assert product_id is not None

    task = await async_client.get(f"/operations/packaging-tasks/{task_id}", headers=headers)
    assert task.status_code == 200, task.text
    line = next(item for item in task.json()["lines"] if item["product_id"] == str(product_id))
    packed = await async_client.post(
        f"/operations/packaging-tasks/{task_id}/lines/{line['id']}/pack",
        headers=headers,
        json={
            "quantity": 1,
            "order_id": str(order_ids[0]),
            "idempotency_key": "cancelled-pack",
        },
    )

    assert packed.status_code == 409, packed.text
    assert packed.json()["detail"] == {
        "code": "order_cancelled",
        "message": "Заказ отменён покупателем, упаковывать нельзя.",
    }
