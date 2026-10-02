"""WMS-632 R2: отмена заказа FBS возвращает подобранную штуку туда, откуда её сняли."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder, FbsOrderProductPick
from app.models.fbs_order_pick import FbsOrderPick
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.warehouse_box import WarehouseBox
from app.services.fbs_cancellation_service import _finish_local_cancellation
from app.services.sorting_location_service import get_or_create_sorting_location
from app.services.wb_marketplace_orders_service import _apply_wb_status_to_order
from tests.test_fbs_picking import (
    _create_product,
    _create_seller_and_warehouse,
    _register_ff_admin,
    _scan_location,
    _scan_product,
    _seed_pick_supply,
)


async def _qty(tenant_id: uuid.UUID, product_id: uuid.UUID, location_id: uuid.UUID) -> int:
    async with SessionLocal() as session:
        value = await session.scalar(
            select(func.coalesce(func.sum(InventoryBalance.quantity_unpacked), 0)).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.product_id == product_id,
                InventoryBalance.storage_location_id == location_id,
            )
        )
        return int(value or 0)


async def _total(tenant_id: uuid.UUID, product_id: uuid.UUID) -> int:
    async with SessionLocal() as session:
        value = await session.scalar(
            select(func.coalesce(func.sum(InventoryBalance.quantity_unpacked), 0)).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.product_id == product_id,
            )
        )
        return int(value or 0)


async def _movement_count(tenant_id: uuid.UUID, product_id: uuid.UUID) -> int:
    async with SessionLocal() as session:
        return int(
            await session.scalar(
                select(func.count(InventoryMovement.id)).where(
                    InventoryMovement.tenant_id == tenant_id,
                    InventoryMovement.product_id == product_id,
                )
            )
            or 0
        )


async def _setup(
    async_client: AsyncClient, *, marketplace: str, stock_qty: int = 1
) -> tuple[dict[str, str], uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, str]:
    headers, suffix, tenant_id = await _register_ff_admin(async_client)
    seller_id, warehouse_id, location_id = await _create_seller_and_warehouse(
        async_client, headers, suffix
    )
    barcode = f"BAR-C632-{suffix[-8:]}"
    product_id = await _create_product(
        async_client, headers, seller_id, sku=f"SKU-C632-{suffix}", barcode=barcode
    )
    supply_id, order_ids, location_code = await _seed_pick_supply(
        async_client, headers, tenant_id, seller_id, warehouse_id, location_id, product_id,
        stock_qty=stock_qty, order_specs=[(1, timedelta(hours=24))], barcode=barcode,
        marketplace=marketplace,
    )
    return (
        headers, tenant_id, warehouse_id, location_id, product_id, supply_id,
        order_ids[0], f"{barcode}|{location_code}",
    )


async def _pick(
    async_client: AsyncClient,
    headers: dict[str, str],
    supply_id: uuid.UUID,
    location_id: uuid.UUID,
    packed: str,
) -> None:
    barcode, location_code = packed.split("|")
    await _scan_location(async_client, headers, supply_id, location_code)
    resp = await _scan_product(
        async_client, headers, supply_id,
        location_id=location_id, barcode=barcode, idempotency_key=str(uuid.uuid4()),
    )
    assert resp.status_code == 200, resp.text


async def _cancel_via_button_path(tenant_id: uuid.UUID, order_id: uuid.UUID) -> None:
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        await _finish_local_cancellation(session, tenant_id, order, actor_user_id=None)
        await session.commit()


@pytest.mark.asyncio
async def test_wb_cancel_order_returns_picked_unit_to_source_cell_once(
    async_client: AsyncClient,
) -> None:
    """C4: подбор из ячейки -> отмена заказа -> штука в ячейке, повтор ничего не двигает."""
    headers, tenant_id, warehouse_id, location_id, product_id, supply_id, order_id, packed = (
        await _setup(async_client, marketplace="wb")
    )
    await _pick(async_client, headers, supply_id, location_id, packed)
    async with SessionLocal() as session:
        sorting = await get_or_create_sorting_location(session, tenant_id, warehouse_id)
        sorting_id = sorting.id
    assert await _qty(tenant_id, product_id, location_id) == 0
    assert await _qty(tenant_id, product_id, sorting_id) == 1
    total_before = await _total(tenant_id, product_id)

    await _cancel_via_button_path(tenant_id, order_id)

    assert await _qty(tenant_id, product_id, location_id) == 1
    assert await _qty(tenant_id, product_id, sorting_id) == 0
    assert await _total(tenant_id, product_id) == total_before
    async with SessionLocal() as session:
        pick = await session.scalar(
            select(FbsOrderPick).where(FbsOrderPick.fbs_order_id == order_id)
        )
        assert pick is not None and pick.undone_at is not None
    moves = await _movement_count(tenant_id, product_id)

    await _cancel_via_button_path(tenant_id, order_id)  # повтор отмены

    assert await _movement_count(tenant_id, product_id) == moves
    assert await _qty(tenant_id, product_id, location_id) == 1
    assert await _qty(tenant_id, product_id, sorting_id) == 0


@pytest.mark.asyncio
async def test_wb_autopoll_cancel_returns_picked_unit_to_source_box(
    async_client: AsyncClient,
) -> None:
    """C4/C5: отмена заказа автоопросом WB возвращает штуку в тот же короб."""
    headers, tenant_id, warehouse_id, location_id, product_id, supply_id, order_id, packed = (
        await _setup(async_client, marketplace="wb")
    )
    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        assert product is not None
        box = WarehouseBox(
            tenant_id=tenant_id,
            warehouse_id=warehouse_id,
            internal_barcode=f"C632-{uuid.uuid4().hex[:12]}",
            container_kind="box",
            storage_location_id=location_id,
        )
        session.add(box)
        await session.flush()
        balance = await session.scalar(
            select(InventoryBalance).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.storage_location_id == location_id,
                InventoryBalance.product_id == product_id,
            )
        )
        assert balance is not None
        balance.container_kind = "box"
        balance.container_id = box.id
        await session.commit()
        box_id = box.id
        box_barcode = box.internal_barcode
    product_barcode = packed.split("|")[0]
    picked = await async_client.post(
        f"/operations/fbs-supplies/{supply_id}/pick/scan",
        headers={**headers, "Idempotency-Key": f"c632-{uuid.uuid4()}"},
        json={
            "barcode": product_barcode,
            "product_id": str(product_id),
            "storage_location_id": str(location_id),
            "container_kind": "box",
            "container_id": str(box_id),
        },
    )
    assert picked.status_code == 200, picked.text
    assert box_barcode
    async with SessionLocal() as session:
        pick = await session.scalar(
            select(FbsOrderPick).where(FbsOrderPick.fbs_order_id == order_id)
        )
        assert pick is not None
        assert pick.source_container_id == box_id

    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_id)
        assert order is not None
        await _apply_wb_status_to_order(session, order, "canceled", actor_user_id=None)
        await session.commit()

    async with SessionLocal() as session:
        in_box = await session.scalar(
            select(func.coalesce(func.sum(InventoryBalance.quantity_unpacked), 0)).where(
                InventoryBalance.tenant_id == tenant_id,
                InventoryBalance.product_id == product_id,
                InventoryBalance.storage_location_id == location_id,
                InventoryBalance.container_id == box_id,
            )
        )
        assert int(in_box or 0) == 1
    assert await _total(tenant_id, product_id) == 1


@pytest.mark.asyncio
async def test_ozon_cancel_order_returns_picked_unit(async_client: AsyncClient) -> None:
    """C5: Ozon — то же самое для позиционного подбора."""
    headers, tenant_id, warehouse_id, location_id, product_id, supply_id, order_id, packed = (
        await _setup(async_client, marketplace="ozon")
    )
    await _pick(async_client, headers, supply_id, location_id, packed)
    async with SessionLocal() as session:
        sorting = await get_or_create_sorting_location(session, tenant_id, warehouse_id)
        sorting_id = sorting.id
    assert await _qty(tenant_id, product_id, sorting_id) == 1

    await _cancel_via_button_path(tenant_id, order_id)

    assert await _qty(tenant_id, product_id, location_id) == 1
    assert await _qty(tenant_id, product_id, sorting_id) == 0
    async with SessionLocal() as session:
        active = await session.scalar(
            select(func.count(FbsOrderProductPick.id)).where(
                FbsOrderProductPick.tenant_id == tenant_id,
                FbsOrderProductPick.undone_at.is_(None),
            )
        )
        assert int(active or 0) == 0
    moves = await _movement_count(tenant_id, product_id)
    await _cancel_via_button_path(tenant_id, order_id)
    assert await _movement_count(tenant_id, product_id) == moves


@pytest.mark.asyncio
async def test_cancel_order_without_picked_unit_moves_nothing(
    async_client: AsyncClient,
) -> None:
    """C6: заказ без подбора — движений нет."""
    _h, tenant_id, _w, location_id, product_id, _s, order_id, _p = await _setup(
        async_client, marketplace="wb"
    )
    moves = await _movement_count(tenant_id, product_id)
    await _cancel_via_button_path(tenant_id, order_id)
    assert await _movement_count(tenant_id, product_id) == moves
    assert await _qty(tenant_id, product_id, location_id) == 1
