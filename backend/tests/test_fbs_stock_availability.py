"""FBS stock availability: formula, FBO isolation, summary, batch queries."""

from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import event

from app.api.fbs_supplies import FbsSupplyPreflightOut
from app.db.session import SessionLocal, engine
from app.models.fbs_order import FbsOrder, FbsOrderReservation
from app.models.inventory_reservation import InventoryReservation
from app.models.marketplace_unload import MarketplaceUnloadLine, MarketplaceUnloadRequest
from app.models.marketplace_unload_reservation import MarketplaceUnloadReservation
from app.models.outbound_shipment import OutboundShipmentLine, OutboundShipmentRequest
from app.models.product import Product
from app.services import inventory_service, stock_direction_service
from app.services.fbs_stock_availability_service import (
    clamp_nonneg,
    fbs_available_qty_by_product,
    fbs_available_qty_for_product,
)
from app.services.sorting_location_service import get_or_create_sorting_location
from app.services.wb_marketplace_orders_service import available_qty_for_fbs_reserve


# TC-NEW-FBS-STOCK-037 — API keeps aggregated stock preflight details.
def test_preflight_response_model_preserves_stock_details() -> None:
    payload = {
        "compatible": True,
        "summary": None,
        "issues": [],
        "server_now": "2026-08-22T00:00:00+00:00",
        "stock_preflight": {
            "compatible": True,
            "recommended_warehouse": {"id": "warehouse-b", "name": "Юг"},
            "warning_lines": [],
            "blocking_lines": [],
        },
    }

    response = FbsSupplyPreflightOut.model_validate(payload)

    assert response.stock_preflight["recommended_warehouse"] == {
        "id": "warehouse-b",
        "name": "Юг",
    }


async def _setup_tenant_product(
    async_client: AsyncClient,
) -> tuple[dict[str, str], uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    suffix = str(time.time_ns())
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"FBS stock {suffix}",
            "slug": f"fbs-stock-{suffix}",
            "admin_email": f"fbs-stock-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    seller = await async_client.post(
        "/sellers", headers=headers, json={"name": f"Seller {suffix}"}
    )
    assert seller.status_code in (200, 201), seller.text
    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "WH", "code": f"wh-{suffix[-8:]}"},
    )
    assert warehouse.status_code in (200, 201), warehouse.text
    location = await async_client.post(
        f"/warehouses/{warehouse.json()['id']}/locations",
        headers=headers,
        json={"code": f"CELL-{suffix[-6:]}"},
    )
    assert location.status_code in (200, 201), location.text
    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "FBS product",
            "sku_code": f"FBS-{suffix}",
            "seller_id": seller.json()["id"],
        },
    )
    assert product.status_code in (200, 201), product.text
    return (
        headers,
        uuid.UUID(seller.json()["id"]),
        uuid.UUID(warehouse.json()["id"]),
        uuid.UUID(product.json()["id"]),
        uuid.UUID(location.json()["id"]),
    )


# TC-NEW-FBS-STOCK-006
@pytest.mark.asyncio
async def test_fbs_availability_without_direction_uses_physical_stock(
    async_client: AsyncClient,
) -> None:
    """No stock direction (reserve) means WB publish/reserve sees physical stock
    minus outbound and FBS reservations — directions are no longer a gate, only
    an extra reserve on top of the physical balance."""
    _headers, seller_id, warehouse_id, product_id, storage_loc_id = (
        await _setup_tenant_product(async_client)
    )

    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        assert product is not None
        tenant_id = product.tenant_id
        sorting = await get_or_create_sorting_location(session, tenant_id, warehouse_id)

        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=storage_loc_id,
            quantity_delta=5,
            movement_type="inbound_intake",
        )
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=sorting.id,
            quantity_delta=2,
            movement_type="inbound_intake",
        )

        outbound = OutboundShipmentRequest(
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            seller_id=seller_id,
            status="submitted",
        )
        session.add(outbound)
        await session.flush()
        outbound_line = OutboundShipmentLine(
            request_id=outbound.id,
            product_id=product_id,
            quantity=1,
            shipped_qty=0,
            storage_location_id=None,
        )
        session.add(outbound_line)
        await session.flush()
        session.add(
            InventoryReservation(
                tenant_id=tenant_id,
                outbound_shipment_line_id=outbound_line.id,
                product_id=product_id,
                warehouse_id=warehouse_id,
                storage_location_id=None,
                quantity=1,
            )
        )

        for idx in range(2):
            order = FbsOrder(
                tenant_id=tenant_id,
                seller_id=seller_id,
                warehouse_id=warehouse_id,
                product_id=product_id,
                wb_order_id=900_000 + idx,
                created_at_wb=product.created_at,
                deadline_at=product.created_at,
                mapping_status="mapped",
                reserve_status="reserved",
            )
            session.add(order)
            await session.flush()
            session.add(
                FbsOrderReservation(
                    tenant_id=tenant_id,
                    fbs_order_id=order.id,
                    product_id=product_id,
                    warehouse_id=warehouse_id,
                    quantity=1,
                )
            )
        await session.commit()

        batch = await fbs_available_qty_by_product(
            session, tenant_id, warehouse_id, [product_id]
        )
        single = await fbs_available_qty_for_product(
            session, tenant_id, warehouse_id, product_id
        )
        via_reserve = await available_qty_for_fbs_reserve(
            session, tenant_id, warehouse_id, product_id
        )

    # on_hand 5 (storage) + 2 (sorting) = 7, minus outbound reserve 1,
    # minus 2 FBS order reservations (1 each) = 4. No direction was created,
    # so there is nothing to subtract for reserves.
    assert batch[product_id] == 4
    assert single == 4
    assert via_reserve == 4


# TC-NEW-FBS-STOCK-005
@pytest.mark.asyncio
async def test_fbo_reserve_does_not_reduce_fbs_publish(async_client: AsyncClient) -> None:
    """MarketplaceUnloadReservation must not change FBS availability."""
    _headers, seller_id, warehouse_id, product_id, storage_loc_id = (
        await _setup_tenant_product(async_client)
    )

    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        assert product is not None
        tenant_id = product.tenant_id
        sorting = await get_or_create_sorting_location(session, tenant_id, warehouse_id)

        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=storage_loc_id,
            quantity_delta=10,
            movement_type="inbound_intake",
        )
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=sorting.id,
            quantity_delta=5,
            movement_type="inbound_intake",
        )
        await stock_direction_service.create_stock_direction(
            session,
            tenant_id,
            product_id,
            name="Reserve",
            quantity=6,
            is_fbs=False,
        )

        before_mp = await fbs_available_qty_for_product(
            session, tenant_id, warehouse_id, product_id
        )

        unload = MarketplaceUnloadRequest(
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            seller_id=seller_id,
            status="collecting",
            ff_modified=False,
            has_discrepancy=False,
        )
        session.add(unload)
        await session.flush()
        unload_line = MarketplaceUnloadLine(
            request_id=unload.id,
            product_id=product_id,
            quantity=99,
        )
        session.add(unload_line)
        await session.flush()
        session.add(
            MarketplaceUnloadReservation(
                tenant_id=tenant_id,
                marketplace_unload_line_id=unload_line.id,
                product_id=product_id,
                warehouse_id=warehouse_id,
                quantity=99,
            )
        )
        await session.commit()

        after_mp = await fbs_available_qty_for_product(
            session, tenant_id, warehouse_id, product_id
        )

    # on_hand 10 (storage) + 5 (sorting) = 15, minus a 6-unit reserve
    # direction = 9. The marketplace-unload reservation must not touch it.
    assert before_mp == 9
    assert after_mp == 9


# TC-NEW-FBS-STOCK-036 — выбранный заказ не блокирует собственный preflight.
@pytest.mark.asyncio
async def test_selected_fbs_order_reservation_can_be_excluded(
    async_client: AsyncClient,
) -> None:
    """A selected order's existing reservation remains available to its supply."""
    _headers, seller_id, warehouse_id, product_id, storage_loc_id = (
        await _setup_tenant_product(async_client)
    )

    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        assert product is not None
        tenant_id = product.tenant_id
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=storage_loc_id,
            quantity_delta=1,
            movement_type="inbound_intake",
        )
        order = FbsOrder(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            wb_order_id=900_036,
            created_at_wb=product.created_at,
            deadline_at=product.created_at,
            mapping_status="mapped",
            reserve_status="reserved",
        )
        session.add(order)
        await session.flush()
        session.add(
            FbsOrderReservation(
                tenant_id=tenant_id,
                fbs_order_id=order.id,
                product_id=product_id,
                warehouse_id=warehouse_id,
                quantity=1,
            )
        )
        await session.commit()

        available = await fbs_available_qty_by_product(
            session,
            tenant_id,
            warehouse_id,
            [product_id],
            exclude_fbs_order_ids=frozenset({order.id}),
        )

    assert available[product_id] == 1


# TC-NEW-FBS-STOCK-007
@pytest.mark.asyncio
async def test_inventory_summary_includes_fbs_reserve(async_client: AsyncClient) -> None:
    """Physical on_hand 3, FBS reserve 1 -> reserved 1, available 2."""
    headers, seller_id, warehouse_id, product_id, storage_loc_id = (
        await _setup_tenant_product(async_client)
    )

    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        assert product is not None
        tenant_id = product.tenant_id

        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=storage_loc_id,
            quantity_delta=3,
            movement_type="inbound_intake",
        )

        order = FbsOrder(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            wb_order_id=901_001,
            created_at_wb=product.created_at,
            deadline_at=product.created_at,
            mapping_status="mapped",
            reserve_status="reserved",
        )
        session.add(order)
        await session.flush()
        session.add(
            FbsOrderReservation(
                tenant_id=tenant_id,
                fbs_order_id=order.id,
                product_id=product_id,
                warehouse_id=warehouse_id,
                quantity=1,
            )
        )
        await session.commit()

    summary = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=headers,
        params={"warehouse_id": str(warehouse_id)},
    )
    assert summary.status_code == 200, summary.text
    row = next(r for r in summary.json() if r["product_id"] == str(product_id))
    assert row["quantity"] == 3
    assert row["reserved"] == 1
    assert row["available"] == 2


# TC-NEW-FBS-STOCK-008 partial + N5
@pytest.mark.asyncio
async def test_negative_computed_amount_clamps_to_zero(async_client: AsyncClient) -> None:
    """N5: over-reserved locally -> publish amount 0."""
    assert clamp_nonneg(-3) == 0

    _headers, seller_id, warehouse_id, product_id, storage_loc_id = (
        await _setup_tenant_product(async_client)
    )

    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        assert product is not None
        tenant_id = product.tenant_id

        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=storage_loc_id,
            quantity_delta=1,
            movement_type="inbound_intake",
        )

        for idx in range(3):
            order = FbsOrder(
                tenant_id=tenant_id,
                seller_id=seller_id,
                warehouse_id=warehouse_id,
                product_id=product_id,
                wb_order_id=902_000 + idx,
                created_at_wb=product.created_at,
                deadline_at=product.created_at,
                mapping_status="mapped",
                reserve_status="reserved",
            )
            session.add(order)
            await session.flush()
            session.add(
                FbsOrderReservation(
                    tenant_id=tenant_id,
                    fbs_order_id=order.id,
                    product_id=product_id,
                    warehouse_id=warehouse_id,
                    quantity=1,
                )
            )
        await session.commit()

        available = await fbs_available_qty_for_product(
            session, tenant_id, warehouse_id, product_id
        )

    assert available == 0


@pytest.mark.asyncio
async def test_fbs_availability_batch_query_count_bounded(
    async_client: AsyncClient,
) -> None:
    """100+ SKUs must not trigger per-SKU query storms."""
    headers, seller_id, warehouse_id, _product_id, storage_loc_id = (
        await _setup_tenant_product(async_client)
    )
    product_ids: list[uuid.UUID] = [_product_id]

    for idx in range(120):
        product = await async_client.post(
            "/products",
            headers=headers,
            json={
                "name": f"Bulk {idx}",
                "sku_code": f"BULK-{time.time_ns()}-{idx}",
                "seller_id": str(seller_id),
            },
        )
        assert product.status_code in (200, 201), product.text
        product_ids.append(uuid.UUID(product.json()["id"]))

    async with SessionLocal() as session:
        first = await session.get(Product, product_ids[0])
        assert first is not None
        tenant_id = first.tenant_id
        for pid in product_ids:
            await inventory_service.record_movement_and_adjust_balance(
                session,
                tenant_id=tenant_id,
                product_id=pid,
                storage_location_id=storage_loc_id,
                quantity_delta=1,
                movement_type="inbound_intake",
            )
        await session.commit()

    query_count = 0

    def _count_query(
        _conn: object,
        _cursor: object,
        _statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        nonlocal query_count
        query_count += 1

    sync_engine = engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", _count_query)
    try:
        async with SessionLocal() as session:
            first = await session.get(Product, product_ids[0])
            assert first is not None
            await fbs_available_qty_by_product(
                session, first.tenant_id, warehouse_id, product_ids
            )
    finally:
        event.remove(sync_engine, "before_cursor_execute", _count_query)

    assert query_count <= 6, f"expected <=6 queries, got {query_count}"


# TC-NEW-FBS-STOCK-035 — STOCKFIX-035: sold must not republish unit to WB
@pytest.mark.asyncio
async def test_sold_release_does_not_resurrect_available_after_fbs_write_off(
    async_client: AsyncClient,
) -> None:
    """physical=5, reserve=1 → publish 4; write-off 1 + sold release → still 4, not 5."""
    _headers, seller_id, warehouse_id, product_id, storage_loc_id = (
        await _setup_tenant_product(async_client)
    )

    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        assert product is not None
        tenant_id = product.tenant_id

        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=storage_loc_id,
            quantity_delta=5,
            movement_type="inbound_intake",
        )
        # No stock direction here: under the new model availability comes
        # straight from physical stock, so a direction is not needed to
        # exercise the write-off/release invariant below.

        order = FbsOrder(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            product_id=product_id,
            wb_order_id=900_035,
            created_at_wb=product.created_at,
            deadline_at=product.created_at,
            mapping_status="mapped",
            reserve_status="reserved",
        )
        session.add(order)
        await session.flush()
        session.add(
            FbsOrderReservation(
                tenant_id=tenant_id,
                fbs_order_id=order.id,
                product_id=product_id,
                warehouse_id=warehouse_id,
                quantity=1,
            )
        )
        await session.commit()

        available_with_reserve = await fbs_available_qty_for_product(
            session, tenant_id, warehouse_id, product_id
        )
        assert available_with_reserve == 4

        await inventory_service.apply_packaging_convert(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=storage_loc_id,
            quantity=1,
        )
        await inventory_service.apply_fbs_supply_write_off(
            session,
            tenant_id=tenant_id,
            product_id=product_id,
            storage_location_id=storage_loc_id,
            quantity=1,
        )

        from app.services.wb_marketplace_orders_service import _release_reservation

        await _release_reservation(session, order)
        await session.commit()

        available_after_sold = await fbs_available_qty_for_product(
            session, tenant_id, warehouse_id, product_id
        )
        assert available_after_sold == 4
        assert available_after_sold != 5
