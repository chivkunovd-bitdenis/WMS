from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.fbs_order import FBS_ORDER_STATUS_CANCELLED, FbsOrder, FbsOrderReservation
from app.models.fbs_packing_box import FbsPackingBoxItem
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.services import fbs_shipment_service
from app.services.sorting_location_service import get_or_create_sorting_location
from tests.test_fbs_shipment_delivery import _mock_actual_composition
from tests.test_fbs_shipment_warehouse_sc import (
    _create_and_fill_physical_box,
    _delivery_preflight,
    _prepare_supply_with_orders,
    _register_ff_admin,
    _setup_seller_with_token,
    enable_wb_marketplace_supplies_mock,  # noqa: F401
)


@pytest.mark.asyncio
@pytest.mark.usefixtures("enable_wb_marketplace_supplies_mock")
@pytest.mark.parametrize("detached", [False, True])
async def test_confirm_excludes_cancelled_box_links_without_stock_return(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    detached: bool,
) -> None:
    # This contract covers local handover, not concurrent stock publication.
    monkeypatch.setattr(
        "app.services.inventory_service.schedule_seller_stock_publish", lambda *args: None,
    )
    headers, suffix = await _register_ff_admin(async_client)
    seller_id, warehouse_id, tenant_id = await _setup_seller_with_token(
        async_client, headers, suffix
    )
    supply, order_ids = await _prepare_supply_with_orders(
        async_client, headers, seller_id, warehouse_id, tenant_id,
        wb_order_ids=[110001, 110002], supply_name="WMS110 exclusions",
    )
    _mock_actual_composition(monkeypatch, {supply["wb_supply_id"]: [110001, 110002]})
    await _create_and_fill_physical_box(async_client, headers, supply["id"], order_ids)
    async with SessionLocal() as session:
        location = await get_or_create_sorting_location(session, tenant_id, uuid.UUID(warehouse_id))
        for order_id in order_ids:
            order = await session.get(FbsOrder, order_id)
            assert order is not None and order.product_id is not None
            session.add(InventoryBalance(
                tenant_id=tenant_id, product_id=order.product_id,
                storage_location_id=location.id, quantity=1,
                quantity_unpacked=1, quantity_packed=0,
            ))
            session.add(FbsOrderReservation(
                tenant_id=tenant_id, fbs_order_id=order.id, product_id=order.product_id,
                warehouse_id=uuid.UUID(warehouse_id), quantity=1,
            ))
            if order.id == order_ids[0]:
                cancelled_product_id = order.product_id
                order.status = FBS_ORDER_STATUS_CANCELLED
                order.picked_at = order.packed_at = None
                if detached:
                    order.supply_id = None
        await session.commit()
        balance = await session.scalar(select(InventoryBalance).where(
            InventoryBalance.product_id == cancelled_product_id
        ))
        assert balance is not None
        original_updated_at = balance.updated_at

    preflight = await _delivery_preflight(async_client, headers, supply["id"])
    assert preflight["can_deliver"] is True
    assert len(preflight["cancelled_orders"]) == 1
    cancelled = preflight["cancelled_orders"][0]
    assert cancelled["order_id"] == str(order_ids[0])
    assert cancelled["wb_order_id"] == 110001
    assert cancelled["article"].startswith("SHIP-110001-")
    assert cancelled["boxes"][0]["box_number"] == 1
    assert cancelled["boxes"][0]["box_barcode"]
    async with SessionLocal() as session:
        assert await session.scalar(select(func.count()).select_from(FbsPackingBoxItem)) == 2
        assert await session.scalar(select(func.count()).select_from(InventoryMovement)) == 0

    real_deliver = fbs_shipment_service.deliver_marketplace_supply
    calls = 0

    async def counted_deliver(*args: Any, **kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        await real_deliver(*args, **kwargs)

    monkeypatch.setattr(fbs_shipment_service, "deliver_marketplace_supply", counted_deliver)
    body = {
        "idempotency_key": str(uuid.uuid4()),
        "confirmed_preflight_version": preflight["version"],
    }
    for _ in range(2):
        response = await async_client.post(
            f"/operations/fbs-supplies/{supply['id']}/deliver", headers=headers, json=body,
        )
        assert response.status_code == 200, response.text
    assert calls == 1
    async with SessionLocal() as session:
        cancelled_order = await session.get(FbsOrder, order_ids[0])
        assert cancelled_order is not None
        assert cancelled_order.supply_id is None and cancelled_order.trbx_id is None
        assert cancelled_order.status == FBS_ORDER_STATUS_CANCELLED
        assert await session.scalar(select(func.count()).select_from(FbsOrderReservation)) == 0
        items = list((await session.scalars(select(FbsPackingBoxItem))).all())
        assert [item.fbs_order_id for item in items] == [order_ids[1]]
        balance = await session.scalar(select(InventoryBalance).where(
            InventoryBalance.product_id == cancelled_product_id
        ))
        assert balance is not None
        assert (balance.quantity, balance.quantity_unpacked, balance.quantity_packed) == (1, 1, 0)
        assert balance.updated_at == original_updated_at
        movements = list((await session.scalars(select(InventoryMovement))).all())
        assert len(movements) == 1
        assert movements[0].product_id != cancelled_product_id
