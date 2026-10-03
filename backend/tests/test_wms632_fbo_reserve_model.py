"""WMS-632 R5-R9: FBO — подбор/укладка только расположение, списание при «Завершить»."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import MOVEMENT_TYPE_MARKETPLACE_UNLOAD, InventoryMovement
from app.models.marketplace_unload import (
    MarketplaceUnloadBox,
    MarketplaceUnloadBoxLine,
    MarketplaceUnloadLine,
    MarketplaceUnloadPickAllocation,
    MarketplaceUnloadRequest,
)
from app.models.marketplace_unload_reservation import MarketplaceUnloadReservation
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.user import User
from app.models.warehouse import Warehouse
from app.services import marketplace_unload_collect_service as collect
from app.services import marketplace_unload_service as mu
from app.services.sorting_location_service import get_or_create_sorting_location


class Ctx:
    tenant: Tenant
    warehouse: Warehouse
    actor: User
    product: Product
    location: StorageLocation
    sorting: StorageLocation
    request: MarketplaceUnloadRequest
    box: MarketplaceUnloadBox


async def _fixture(session: AsyncSession, *, stock: int = 10, plan: int = 5) -> Ctx:
    suffix = uuid.uuid4().hex[:8]
    ctx = Ctx()
    ctx.tenant = Tenant(name="WMS-632", slug=f"wms632-fbo-{suffix}")
    session.add(ctx.tenant)
    await session.flush()
    ctx.warehouse = Warehouse(tenant_id=ctx.tenant.id, name="W", code=f"w632-{suffix}")
    seller = Seller(tenant_id=ctx.tenant.id, name="seller")
    ctx.actor = User(
        tenant_id=ctx.tenant.id,
        email=f"wms632-{suffix}@example.test",
        password_hash="unused",
        role="fulfillment_admin",
    )
    session.add_all((ctx.warehouse, seller, ctx.actor))
    await session.flush()
    ctx.product = Product(
        tenant_id=ctx.tenant.id, seller_id=seller.id, name="P", sku_code=f"wms632-{suffix}"
    )
    ctx.location = StorageLocation(
        tenant_id=ctx.tenant.id,
        warehouse_id=ctx.warehouse.id,
        code=f"A-{suffix}",
        barcode=f"A-{suffix}",
    )
    ctx.request = MarketplaceUnloadRequest(
        tenant_id=ctx.tenant.id,
        warehouse_id=ctx.warehouse.id,
        seller_id=seller.id,
        marketplace="ozon",
        status="confirmed",
        planned_shipment_date=(datetime.now(UTC) + timedelta(days=1)).date(),
    )
    session.add_all((ctx.product, ctx.location, ctx.request))
    await session.flush()
    ctx.sorting = await get_or_create_sorting_location(session, ctx.tenant.id, ctx.warehouse.id)
    line = MarketplaceUnloadLine(
        request_id=ctx.request.id, product_id=ctx.product.id, quantity=plan
    )
    session.add(line)
    await session.flush()
    session.add(
        MarketplaceUnloadReservation(
            tenant_id=ctx.tenant.id,
            marketplace_unload_line_id=line.id,
            product_id=ctx.product.id,
            warehouse_id=ctx.warehouse.id,
            quantity=plan,
        )
    )
    session.add(
        InventoryBalance(
            tenant_id=ctx.tenant.id,
            product_id=ctx.product.id,
            storage_location_id=ctx.location.id,
            quantity=stock,
            quantity_unpacked=stock,
            quantity_packed=0,
        )
    )
    ctx.box = MarketplaceUnloadBox(request_id=ctx.request.id, box_preset="60_40_40")
    session.add(ctx.box)
    await session.commit()
    return ctx


async def _qty(session: AsyncSession, ctx: Ctx, location_id: uuid.UUID | None = None) -> int:
    stmt = select(func.coalesce(func.sum(InventoryBalance.quantity), 0)).where(
        InventoryBalance.product_id == ctx.product.id
    )
    if location_id is not None:
        stmt = stmt.where(InventoryBalance.storage_location_id == location_id)
    return int(await session.scalar(stmt) or 0)


async def _reserved(session: AsyncSession, ctx: Ctx) -> int:
    return int(
        await session.scalar(
            select(func.coalesce(func.sum(MarketplaceUnloadReservation.quantity), 0)).where(
                MarketplaceUnloadReservation.product_id == ctx.product.id
            )
        )
        or 0
    )


async def _unload_moves(session: AsyncSession, ctx: Ctx) -> list[int]:
    rows = await session.scalars(
        select(InventoryMovement.quantity_delta)
        .where(
            InventoryMovement.product_id == ctx.product.id,
            InventoryMovement.movement_type == MOVEMENT_TYPE_MARKETPLACE_UNLOAD,
        )
        .order_by(InventoryMovement.created_at, InventoryMovement.id)
    )
    return list(rows)


async def _box_line(session: AsyncSession, ctx: Ctx) -> MarketplaceUnloadBoxLine:
    return (
        await session.scalars(
            select(MarketplaceUnloadBoxLine).where(
                MarketplaceUnloadBoxLine.box_id == ctx.box.id
            )
        )
    ).one()


async def _pick(session: AsyncSession, ctx: Ctx, quantity: int) -> None:
    await collect.record_pick_allocation(
        session,
        ctx.tenant.id,
        ctx.request.id,
        storage_location_id=ctx.location.id,
        product_id=ctx.product.id,
        quantity=quantity,
        actor_user_id=ctx.actor.id,
    )


async def _box(session: AsyncSession, ctx: Ctx, quantity: int):
    result = await collect.collect_into_box(
        session,
        ctx.tenant.id,
        ctx.request.id,
        box_id=ctx.box.id,
        storage_location_id=ctx.location.id,
        product_id=ctx.product.id,
        quantity=quantity,
        actor_user_id=ctx.actor.id,
    )
    await session.commit()
    return result


@pytest.mark.asyncio
async def test_pick_and_box_only_move_location_and_keep_reserve(db_session) -> None:
    """C10/C11: подбор и укладка — расположение; остаток, резерв, списаний нет."""
    ctx = await _fixture(db_session)
    await _pick(db_session, ctx, 3)
    assert await _qty(db_session, ctx, ctx.location.id) == 7
    assert await _qty(db_session, ctx, ctx.sorting.id) == 3
    assert await _qty(db_session, ctx) == 10
    assert await _reserved(db_session, ctx) == 5
    assert await _unload_moves(db_session, ctx) == []

    await _box(db_session, ctx, 1)
    assert await _qty(db_session, ctx) == 10
    assert await _reserved(db_session, ctx) == 5
    assert await _unload_moves(db_session, ctx) == []

    # выемка из короба и уменьшение подбора возвращают штуку в исходную ячейку
    line_id = (await _box_line(db_session, ctx)).id
    await collect.remove_from_box(
        db_session, ctx.tenant.id, ctx.request.id, box_id=ctx.box.id, line_id=line_id,
        quantity=1, actor_user_id=ctx.actor.id,
    )
    await collect.set_pick_allocation(
        db_session, ctx.tenant.id, ctx.request.id, product_id=ctx.product.id,
        storage_location_id=ctx.location.id, quantity=1, actor_user_id=ctx.actor.id,
    )
    assert await _qty(db_session, ctx, ctx.location.id) == 9
    assert await _qty(db_session, ctx, ctx.sorting.id) == 1
    assert await _qty(db_session, ctx) == 10
    assert await _reserved(db_session, ctx) == 5
    assert await _unload_moves(db_session, ctx) == []


@pytest.mark.asyncio
async def test_complete_writes_off_fact_once_and_releases_reserve(db_session) -> None:
    """C12: «Завершить» списывает уложенное один раз, резерв снимается."""
    ctx = await _fixture(db_session)
    await _pick(db_session, ctx, 2)
    await _box(db_session, ctx, 2)  # подобрано 4, уложено в короб 2: факт = 2
    fact = 2
    tenant_id, request_id, actor_id = ctx.tenant.id, ctx.request.id, ctx.actor.id
    await db_session.refresh(ctx.box, ["lines"])
    await db_session.refresh(ctx.request, ["boxes"])
    done = await mu.complete_unload(
        db_session, tenant_id, request_id, acknowledge_discrepancy=True,
        performer_id=actor_id,
    )
    assert done.status == "shipped"
    assert await _unload_moves(db_session, ctx) == [-fact]
    assert await _qty(db_session, ctx) == 10 - fact
    assert await _reserved(db_session, ctx) == 0

    with pytest.raises(mu.MarketplaceUnloadError):
        await mu.complete_unload(
            db_session, tenant_id, request_id, acknowledge_discrepancy=True,
            performer_id=actor_id,
        )
    assert await _unload_moves(db_session, ctx) == [-fact]
    # повторный проход списания (например, после сбоя) ничего не добавляет
    req = await mu.get_request(db_session, ctx.tenant.id, ctx.request.id)
    assert req is not None
    await mu._write_off_shipped_fact(
        db_session, req, mu.distributed_qty_by_product(req), actor_user_id=actor_id
    )
    await db_session.commit()
    assert await _unload_moves(db_session, ctx) == [-fact]
    assert await _qty(db_session, ctx) == 10 - fact


@pytest.mark.asyncio
async def test_complete_after_legacy_pick_deduction_writes_only_difference(db_session) -> None:
    """C14/R8: документ, уже списавший 2 шт при подборе, не задваивается."""
    ctx = await _fixture(db_session, stock=8)  # 10 минус 2 уже списанные
    session = db_session
    session.add(
        MarketplaceUnloadPickAllocation(
            request_id=ctx.request.id,
            product_id=ctx.product.id,
            storage_location_id=ctx.location.id,
            quantity=2,
        )
    )
    session.add(
        InventoryMovement(
            tenant_id=ctx.tenant.id,
            product_id=ctx.product.id,
            storage_location_id=ctx.location.id,
            warehouse_id=ctx.warehouse.id,
            quantity_delta=-2,
            movement_type=MOVEMENT_TYPE_MARKETPLACE_UNLOAD,
            marketplace_unload_request_id=ctx.request.id,
            actor_user_id=ctx.actor.id,
        )
    )
    await session.commit()
    await _box(session, ctx, 1)  # новая штука уже по новым правилам: на сортировке
    assert await _qty(session, ctx) == 8
    # короб с 3 штуками факта: 2 исторических + 1 новая
    box_line = await _box_line(session, ctx)
    box_line.quantity = 3
    await session.commit()

    await mu.complete_unload(
        session, ctx.tenant.id, ctx.request.id, acknowledge_discrepancy=True,
        performer_id=ctx.actor.id,
    )
    assert sorted(await _unload_moves(session, ctx)) == [-2, -1]
    assert await _qty(session, ctx) == 10 - 3
    assert await _reserved(session, ctx) == 0


@pytest.mark.asyncio
async def test_cancel_returns_units_to_source_and_releases_reserve(db_session) -> None:
    """C13/R9: отмена в collecting — штуки в исходной ячейке, резерв снят, лишнего прихода нет."""
    ctx = await _fixture(db_session)
    await _pick(db_session, ctx, 3)
    await _box(db_session, ctx, 1)
    assert await _qty(db_session, ctx, ctx.sorting.id) == 4

    cancelled = await mu.cancel_request(
        db_session, ctx.tenant.id, ctx.request.id, performer_id=ctx.actor.id
    )
    assert cancelled.status == "cancelled"
    assert await _qty(db_session, ctx, ctx.location.id) == 10
    assert await _qty(db_session, ctx, ctx.sorting.id) == 0
    assert await _qty(db_session, ctx) == 10
    assert await _reserved(db_session, ctx) == 0
    assert await _unload_moves(db_session, ctx) == []


@pytest.mark.asyncio
async def test_cancel_legacy_document_credits_deducted_units_once(db_session) -> None:
    """R8/R9: у документа со старым списанием отмена возвращает его ровно один раз."""
    ctx = await _fixture(db_session, stock=8)
    db_session.add(
        MarketplaceUnloadPickAllocation(
            request_id=ctx.request.id,
            product_id=ctx.product.id,
            storage_location_id=ctx.location.id,
            quantity=2,
        )
    )
    db_session.add(
        InventoryMovement(
            tenant_id=ctx.tenant.id,
            product_id=ctx.product.id,
            storage_location_id=ctx.location.id,
            warehouse_id=ctx.warehouse.id,
            quantity_delta=-2,
            movement_type=MOVEMENT_TYPE_MARKETPLACE_UNLOAD,
            marketplace_unload_request_id=ctx.request.id,
            actor_user_id=ctx.actor.id,
        )
    )
    await db_session.commit()
    await _pick(db_session, ctx, 1)  # новая штука: сортировка
    await mu.cancel_request(db_session, ctx.tenant.id, ctx.request.id, performer_id=ctx.actor.id)
    assert await _qty(db_session, ctx) == 10
    assert await _qty(db_session, ctx, ctx.sorting.id) == 0
    assert sum(await _unload_moves(db_session, ctx)) == 0
