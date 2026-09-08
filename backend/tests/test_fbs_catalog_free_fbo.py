from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from app.db.session import SessionLocal
from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.models.fbs_order import FbsOrder, FbsOrderReservation
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.inventory_balance import InventoryBalance
from app.models.product import Product
from app.models.stock_direction import StockDirection
from app.services import inventory_service, stock_direction_service
from tests.test_stock_directions import _seed_stocked_product


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "units_mode,physical,direction_qty,reserve_qty,expected_free",
    [(False, 1, 0, 1, 0), (False, 10, 2, 3, 5), (True, 10, 2, 3, 3)],
)
async def test_catalog_free_fbo_excludes_order_reserves_in_both_modes(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    units_mode: bool,
    physical: int,
    direction_qty: int,
    reserve_qty: int,
    expected_free: int,
) -> None:
    monkeypatch.setattr(inventory_service, "schedule_seller_stock_publish", lambda *a: None)
    monkeypatch.setattr(stock_direction_service, "schedule_seller_stock_publish", lambda *a: None)
    headers, seller_id, _, warehouse_id, _, product_id = await _seed_stocked_product(async_client)
    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        assert product is not None
        product.fbs_units_mode = units_mode
        await session.execute(update(InventoryBalance).where(
            InventoryBalance.product_id == product_id,
        ).values(quantity=physical, quantity_unpacked=physical, quantity_packed=0))
        binding = FbsWarehouseBinding(
            tenant_id=product.tenant_id, seller_id=uuid.UUID(seller_id),
            wms_warehouse_id=warehouse_id, wb_warehouse_id=580060,
        )
        session.add(binding)
        await session.flush()
        # Saved unit allocations must stay inactive in percentage mode.
        session.add(FbsBindingStockPool(
            tenant_id=product.tenant_id, binding_id=binding.id,
            product_id=product_id, quantity=2,
        ))
        if direction_qty:
            session.add(StockDirection(
                tenant_id=product.tenant_id, product_id=product_id,
                name="Ordinary reserve", quantity=direction_qty, is_fbs=False,
            ))
        order = FbsOrder(
            tenant_id=product.tenant_id, seller_id=uuid.UUID(seller_id),
            warehouse_id=warehouse_id, product_id=product_id, wb_order_id=580060,
            created_at_wb=product.created_at, deadline_at=product.created_at,
            mapping_status="mapped", reserve_status="reserved",
        )
        session.add(order)
        await session.flush()
        reservation = FbsOrderReservation(
            tenant_id=product.tenant_id, fbs_order_id=order.id,
            product_id=product_id, warehouse_id=warehouse_id, quantity=reserve_qty,
        )
        session.add(reservation)
        await session.commit()
        reservation_id = reservation.id

    async def read_summary() -> dict:
        response = await async_client.get(
            "/operations/inventory-balances/summary", headers=headers,
            params={"warehouse_id": str(warehouse_id)},
        )
        assert response.status_code == 200, response.text
        return next(row for row in response.json() if row["product_id"] == str(product_id))

    row = await read_summary()
    assert row["quantity"] == physical
    assert row["reserved"] == reserve_qty
    assert row["quantity_free_fbo"] == expected_free
    assert row["available"] == expected_free
    assert row["quantity_fbs"] == (2 + reserve_qty if units_mode else 0)
    picker = await async_client.get(
        "/operations/marketplace-unload-requests/available-products",
        headers=headers, params={"warehouse_id": str(warehouse_id), "seller_id": seller_id},
    )
    assert picker.status_code == 200, picker.text
    picked_row = next(item for item in picker.json() if item["product_id"] == str(product_id))
    assert picked_row["available"] == expected_free

    # Releasing the existing reservation changes only derived availability.
    async with SessionLocal() as session:
        reservation = await session.get(FbsOrderReservation, reservation_id)
        assert reservation is not None
        await session.delete(reservation)
        await session.commit()
    reread = await read_summary()
    assert reread["quantity"] == physical
    assert reread["quantity_free_fbo"] == expected_free + reserve_qty
