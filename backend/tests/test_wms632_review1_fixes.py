"""WMS-632, круг 2: исправления по ревью Astra (D1, D2, D3, D5; D4 отменён решением владельца)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.models.fbs_order import RESERVE_STATUS_RESERVED, FbsOrderReservation
from app.models.inventory_balance import InventoryBalance
from app.models.storage_location import StorageLocation
from app.models.warehouse_box import WarehouseBox
from app.services import inventory_service
from app.services import marketplace_unload_collect_service as collect
from app.services import marketplace_unload_service as mu
from app.services import pick_option_location_service as pick_location
from app.services.marketplace_unload_pick_service import MarketplaceUnloadPickError
from tests.test_fbs_ozon_lane import _seed_ozon_supply_case
from tests.test_wms632_fbo_reserve_model import (
    Ctx,
    _box,
    _fixture,
    _pick,
    _qty,
)


@pytest.mark.asyncio
async def test_d1_staged_unit_on_sorting_cannot_be_picked_again(db_session) -> None:
    ctx = await _fixture(db_session)
    await _box(db_session, ctx, 1)  # ячейка 9, сортировка 1
    assert await _qty(db_session, ctx, ctx.sorting.id) == 1
    available = await pick_location.available_pick_source_quantity(
        db_session, ctx.tenant.id, ctx.product.id, ctx.sorting.id,
        marketplace_unload_request_id=ctx.request.id,
    )
    assert available == 0
    # то же видно соседнему подбору (FBS): штука занята документом
    fbs_available = await pick_location.available_pick_source_quantity(
        db_session, ctx.tenant.id, ctx.product.id, ctx.sorting.id,
    )
    assert fbs_available == 0
    with pytest.raises(MarketplaceUnloadPickError, match="insufficient_available"):
        await collect.collect_into_box(
            db_session, ctx.tenant.id, ctx.request.id, box_id=ctx.box.id,
            storage_location_id=ctx.sorting.id, product_id=ctx.product.id, quantity=1,
            actor_user_id=ctx.actor.id,
        )
    # штука из ячейки по-прежнему доступна
    await _box(db_session, ctx, 1)
    assert await _qty(db_session, ctx, ctx.sorting.id) == 2


async def _committed_ctx_with_boxed(units: int) -> tuple[Ctx, uuid.UUID, uuid.UUID, uuid.UUID]:
    async with SessionLocal() as s:
        ctx = await _fixture(s)
        await _pick(s, ctx, units)
        await _box(s, ctx, units)
        return ctx, ctx.tenant.id, ctx.request.id, ctx.actor.id


@pytest.mark.asyncio
async def test_d2_cancel_with_stale_collecting_status_does_not_return_shipped_stock(
    async_client,
) -> None:
    ctx, tenant_id, request_id, actor_id = await _committed_ctx_with_boxed(1)
    product_id = ctx.product.id
    async with SessionLocal() as sa, SessionLocal() as sb:
        stale = await mu.get_request(sa, tenant_id, request_id)
        assert stale is not None and stale.status == "collecting"
        await mu.complete_unload(
            sb, tenant_id, request_id, acknowledge_discrepancy=True, performer_id=actor_id
        )
        # сессия A действует по ранее прочитанному (устаревшему) объекту
        result = await mu.cancel_request(sa, tenant_id, request_id, performer_id=actor_id)
        assert result.status == "shipped"  # проведённый документ не возвращает остаток
    async with SessionLocal() as s:
        total = await s.scalar(
            select(func.sum(InventoryBalance.quantity)).where(
                InventoryBalance.product_id == product_id
            )
        )
        moves = list(
            await s.scalars(
                select(inventory_service.InventoryMovement.quantity_delta).where(
                    inventory_service.InventoryMovement.product_id == product_id,
                    inventory_service.InventoryMovement.movement_type == "marketplace_unload",
                )
            )
        )
    assert int(total or 0) == 9
    assert moves == [-1]


@pytest.mark.asyncio
async def test_d2_complete_after_cancel_is_rejected_and_stock_intact(async_client) -> None:
    ctx, tenant_id, request_id, actor_id = await _committed_ctx_with_boxed(1)
    product_id = ctx.product.id
    async with SessionLocal() as sa, SessionLocal() as sb:
        stale = await mu.get_request(sa, tenant_id, request_id)
        assert stale is not None and stale.status == "collecting"
        await mu.cancel_request(sb, tenant_id, request_id, performer_id=actor_id)
        with pytest.raises(mu.MarketplaceUnloadError):
            await mu.complete_unload(
                sa, tenant_id, request_id, acknowledge_discrepancy=True, performer_id=actor_id
            )
    async with SessionLocal() as s:
        total = await s.scalar(
            select(func.sum(InventoryBalance.quantity)).where(
                InventoryBalance.product_id == product_id
            )
        )
    assert int(total or 0) == 10


@pytest.mark.asyncio
async def test_d3_units_mode_without_pool_still_reserves(db_session) -> None:
    tenant, _seller, warehouse, product, order, _supply = await _seed_ozon_supply_case(
        db_session, packed=False
    )
    order.marketplace = "wb"
    order.reserve_status = "new"
    product.fbs_units_mode = True
    location = StorageLocation(
        tenant_id=tenant.id, warehouse_id=warehouse.id, code="D3", barcode="D3"
    )
    db_session.add(location)
    await db_session.flush()
    db_session.add(
        InventoryBalance(
            tenant_id=tenant.id, product_id=product.id, storage_location_id=location.id,
            quantity=5, quantity_unpacked=5, quantity_packed=0,
        )
    )
    await db_session.commit()
    await inventory_service.update_fbs_order_reservation(db_session, order, reserve=True)
    await db_session.commit()
    assert order.reserve_status == RESERVE_STATUS_RESERVED
    reservations = await db_session.scalar(
        select(func.count()).select_from(FbsOrderReservation).where(
            FbsOrderReservation.fbs_order_id == order.id
        )
    )
    pools = await db_session.scalar(select(func.count()).select_from(FbsBindingStockPool))
    assert reservations == 1
    assert pools == 0  # публикацию и лимит не создаём


@pytest.mark.asyncio
async def test_d5_remove_from_shipment_box_returns_unit_to_source_container(db_session) -> None:
    ctx = await _fixture(db_session)
    session = db_session
    source_box = WarehouseBox(
        tenant_id=ctx.tenant.id,
        warehouse_id=ctx.warehouse.id,
        internal_barcode=f"D5-{uuid.uuid4().hex[:10]}",
        container_kind="box",
        storage_location_id=ctx.location.id,
    )
    session.add(source_box)
    await session.flush()
    balance = await session.scalar(
        select(InventoryBalance).where(
            InventoryBalance.product_id == ctx.product.id,
            InventoryBalance.storage_location_id == ctx.location.id,
        )
    )
    assert balance is not None
    balance.container_kind = "box"
    balance.container_id = source_box.id
    await session.commit()
    source_box_id, location_id = source_box.id, ctx.location.id
    tenant_id, request_id, box_id = ctx.tenant.id, ctx.request.id, ctx.box.id
    product_id, actor_id = ctx.product.id, ctx.actor.id

    await collect.collect_into_box(
        session, tenant_id, request_id, box_id=box_id, storage_location_id=location_id,
        product_id=product_id, quantity=1, actor_user_id=actor_id,
        container_kind="box", container_id=source_box_id,
    )
    await session.commit()
    line_id = (await session.scalars(
        select(collect.MarketplaceUnloadBoxLine).where(
            collect.MarketplaceUnloadBoxLine.box_id == box_id
        )
    )).one().id
    await collect.remove_from_box(
        session, tenant_id, request_id, box_id=box_id, line_id=line_id, quantity=1,
        actor_user_id=actor_id,
    )
    rows = (
        await session.execute(
            select(InventoryBalance.container_id, InventoryBalance.quantity).where(
                InventoryBalance.product_id == product_id,
                InventoryBalance.storage_location_id == location_id,
            )
        )
    ).all()
    by_container = {cid: int(qty) for cid, qty in rows}
    assert by_container.get(source_box_id) == 10
    assert by_container.get(None, 0) == 0
