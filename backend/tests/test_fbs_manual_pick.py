"""Manual FBS pick API: cell selection and explicit order confirmation."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.fbs_order import PACK_STATUS_PACKED, FbsOrder
from app.models.fbs_order_pick import FbsOrderPick
from app.models.inventory_balance import InventoryBalance
from tests.test_fbs_picking import (
    _create_product,
    _create_seller_and_warehouse,
    _register_ff_admin,
    _seed_pick_supply,
)


async def _select_manual_location(
    async_client: AsyncClient,
    headers: dict[str, str],
    supply_id: uuid.UUID,
    location_id: uuid.UUID,
) -> Any:
    return await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/pick/manual/location",
        headers=headers,
        json={"location_id": str(location_id)},
    )


async def _manual_pick(
    async_client: AsyncClient,
    headers: dict[str, str],
    supply_id: uuid.UUID,
    *,
    location_id: uuid.UUID,
    product_id: uuid.UUID,
    order_id: uuid.UUID,
    idempotency_key: str,
) -> Any:
    return await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/pick/manual",
        headers=headers,
        json={
            "location_id": str(location_id),
            "product_id": str(product_id),
            "order_id": str(order_id),
            "idempotency_key": idempotency_key,
        },
    )


@pytest.mark.asyncio
async def test_manual_pick_selects_cell_and_picks_explicit_order_idempotently(
    async_client: AsyncClient,
) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix
    )
    barcode = f"BAR-MANUAL-{suffix[-8:]}"
    product_id = await _create_product(
        async_client, headers, seller_id, sku=f"SKU-M-{suffix}", barcode=barcode
    )
    supply_id, order_ids, _location_code = await _seed_pick_supply(
        async_client,
        headers,
        tenant_id,
        seller_id,
        warehouse_id,
        location_id,
        product_id,
        stock_qty=2,
        order_specs=[(1, timedelta(hours=24)), (2, timedelta(hours=48))],
        barcode=barcode,
    )

    selected = await _select_manual_location(
        async_client, headers, supply_id, location_id
    )
    assert selected.status_code == 200, selected.text
    choice = selected.json()
    assert choice["id"] == str(location_id)
    assert choice["expected_products"][0]["product_id"] == str(product_id)
    assert choice["expected_products"][0]["remaining_qty"] == 2

    key = str(uuid.uuid4())
    first = await _manual_pick(
        async_client,
        headers,
        supply_id,
        location_id=location_id,
        product_id=product_id,
        order_id=order_ids[1],
        idempotency_key=key,
    )
    retry = await _manual_pick(
        async_client,
        headers,
        supply_id,
        location_id=location_id,
        product_id=product_id,
        order_id=order_ids[1],
        idempotency_key=key,
    )
    assert first.status_code == retry.status_code == 200
    assert first.json()["progress"]["picked"] == retry.json()["progress"]["picked"] == 1
    picked = next(order for order in retry.json()["orders"] if order["id"] == str(order_ids[1]))
    assert picked["pick"]["status"] == "picked"

    reused = await _manual_pick(
        async_client,
        headers,
        supply_id,
        location_id=location_id,
        product_id=product_id,
        order_id=order_ids[0],
        idempotency_key=key,
    )
    assert reused.status_code == 409
    assert reused.json()["detail"]["code"] == "idempotency_key_reused"


@pytest.mark.asyncio
async def test_manual_pick_rejects_wrong_cell_product_and_allows_packed_order(
    async_client: AsyncClient,
) -> None:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix
    )
    barcode = f"BAR-MANUAL-GUARD-{suffix[-8:]}"
    product_id = await _create_product(
        async_client, headers, seller_id, sku=f"SKU-MG-{suffix}", barcode=barcode
    )
    other_product_id = await _create_product(
        async_client,
        headers,
        seller_id,
        sku=f"SKU-OTHER-{suffix}",
        barcode=f"OTHER-{suffix[-8:]}",
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
        order_specs=[(1, timedelta(hours=24))],
        barcode=barcode,
    )

    _seller, _warehouse, foreign_location_id = await _create_seller_and_warehouse(
        async_client, headers, f"{suffix}-other"
    )
    wrong_warehouse = await _select_manual_location(
        async_client, headers, supply_id, foreign_location_id
    )
    assert wrong_warehouse.status_code == 404
    assert wrong_warehouse.json()["detail"]["code"] == "wrong_location"

    foreign = await _manual_pick(
        async_client,
        headers,
        supply_id,
        location_id=location_id,
        product_id=other_product_id,
        order_id=order_ids[0],
        idempotency_key=str(uuid.uuid4()),
    )
    assert foreign.status_code == 409
    assert foreign.json()["detail"]["code"] == "product_not_in_supply"

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_ids[0])
        assert order is not None
        order.pack_status = PACK_STATUS_PACKED
        await session.commit()

    packed = await _manual_pick(
        async_client,
        headers,
        supply_id,
        location_id=location_id,
        product_id=product_id,
        order_id=order_ids[0],
        idempotency_key=str(uuid.uuid4()),
    )
    assert packed.status_code == 200, packed.text
    picked_order = next(
        order for order in packed.json()["orders"] if order["id"] == str(order_ids[0])
    )
    assert picked_order["pick"]["status"] == "picked"

    async with SessionLocal() as session:
        stored_pick = await session.scalar(
            select(FbsOrderPick).where(FbsOrderPick.fbs_order_id == order_ids[0])
        )
        source_balance = await session.scalar(
            select(InventoryBalance.quantity_unpacked).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.product_id == product_id,
                InventoryBalance.storage_location_id == location_id,
            )
        )
        assert stored_pick is not None
        assert stored_pick.source_storage_location_id == location_id
        assert stored_pick.inventory_movement_id is None
        assert int(source_balance or 0) == 1
