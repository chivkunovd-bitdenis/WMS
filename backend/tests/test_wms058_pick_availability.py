"""WMS-058: one real source, one assignment, FBS stock protected from FBO."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_order import FbsOrder, FbsOrderProduct, FbsOrderReservation
from app.models.fbs_supply import FbsSupply
from app.models.inventory_balance import InventoryBalance
from app.models.marketplace_unload import MarketplaceUnloadLine, MarketplaceUnloadRequest
from app.models.storage_location import StorageLocation
from app.models.user import User
from app.models.warehouse_box import WarehouseBox
from app.services import fbs_picking_service as picking
from app.services import marketplace_unload_collect_service as collect
from app.services import marketplace_unload_pick_service as mp_pick
from app.services.sorting_location_service import get_or_create_sorting_location
from tests.test_fbs_ozon_lane import _seed_ozon_supply_case


async def seed(session: AsyncSession, *, kind: str = "loose", marketplace: str = "wb"):
    tenant, seller, warehouse, product, order, supply = await _seed_ozon_supply_case(
        session, packed=True
    )
    assert supply is not None
    supply.marketplace = marketplace
    supply.status = "assembling"
    order.marketplace = marketplace
    order.status = "assembling"
    order.pick_status = "pending"
    order.pack_status = "packed"
    actor = User(
        tenant_id=tenant.id,
        email="wms058@example.com",
        password_hash="test",
        role="fulfillment_admin",
    )
    session.add(actor)
    if kind == "sorting":
        location = await get_or_create_sorting_location(session, tenant.id, warehouse.id)
    else:
        location = StorageLocation(
            tenant_id=tenant.id, warehouse_id=warehouse.id, code="A", barcode="A"
        )
        session.add(location)
    await session.flush()
    box = None
    if kind == "box":
        box = WarehouseBox(
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            storage_location_id=location.id,
            internal_barcode="BOX",
        )
        session.add(box)
        await session.flush()
    session.add(
        InventoryBalance(
            tenant_id=tenant.id,
            product_id=product.id,
            storage_location_id=location.id,
            container_kind="box" if box else None,
            container_id=box.id if box else None,
            quantity=1,
            quantity_unpacked=1,
            quantity_packed=0,
        )
    )
    if marketplace == "ozon":
        session.add(
            FbsOrderProduct(
                order_id=order.id,
                product_id=product.id,
                ozon_sku=3001,
                quantity=1,
                position_index=0,
            )
        )
    await session.commit()
    return tenant, seller, warehouse, product, order, supply, actor, location, box


async def balances(session, product):
    rows = await session.execute(
        select(
            InventoryBalance.storage_location_id,
            InventoryBalance.container_id,
            InventoryBalance.quantity,
        ).where(InventoryBalance.product_id == product.id)
    )
    return {(loc, container): qty for loc, container, qty in rows.all() if qty}


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["loose", "box", "sorting"])
async def test_two_wb_supplies_cannot_assign_same_physical_unit(
    db_session: AsyncSession, kind: str
):
    s = db_session
    tenant, seller, warehouse, product, order, supply, actor, location, box = await seed(
        s, kind=kind
    )
    other = FbsSupply(
        tenant_id=tenant.id,
        seller_id=seller.id,
        warehouse_id=warehouse.id,
        marketplace="wb",
        status="assembling",
        name="Second",
        delivery_type="warehouse_sc",
    )
    s.add(other)
    await s.flush()
    second = FbsOrder(
        tenant_id=tenant.id,
        seller_id=seller.id,
        warehouse_id=warehouse.id,
        product_id=product.id,
        supply_id=other.id,
        marketplace="wb",
        wb_order_id=3999,
        mapping_status="mapped",
        reserve_status="reserved",
        created_at_wb=datetime.now(UTC),
        deadline_at=datetime.now(UTC) + timedelta(days=1),
        status="assembling",
        pick_status="pending",
    )
    s.add(second)
    s.add(
        FbsOrderReservation(
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            product_id=product.id,
            fbs_order_id=order.id,
            quantity=1,
        )
    )
    await s.commit()
    before = await balances(s, product)
    args = dict(
        location_id=location.id,
        product_id=product.id,
        container_kind="box" if box else None,
        container_id=box.id if box else None,
        actor=actor,
    )
    await picking.manual_pick_product(
        s, tenant.id, supply.id, order_id=order.id, idempotency_key="first", **args
    )
    await s.commit()
    options = await picking.get_pick_options(s, tenant.id, other.id)
    row = next(row for row in options[0].locations if row.storage_location_id == location.id)
    assert row.available == 0
    assert row.sources[0].quantity == 1
    assert row.sources[0].available == 0
    with pytest.raises(picking.FbsPickingError, match="insufficient_unpacked"):
        await picking.manual_pick_product(
            s, tenant.id, other.id, order_id=second.id, idempotency_key="second", **args
        )
    await picking.undo_pick(
        s, tenant.id, supply.id, order.id, idempotency_key="undo-first", actor=actor
    )
    await s.commit()
    await picking.manual_pick_product(
        s, tenant.id, other.id, order_id=second.id, idempotency_key="second-retry", **args
    )
    await s.commit()
    assert await balances(s, product) == before


@pytest.mark.asyncio
async def test_ozon_undo_returns_to_original_box_and_repeat_pick_is_single(
    db_session: AsyncSession,
):
    s = db_session
    tenant, _, _, product, order, supply, actor, location, box = await seed(
        s, kind="box", marketplace="ozon"
    )
    assert box is not None
    before = await balances(s, product)
    args = dict(
        location_id=location.id,
        product_id=product.id,
        order_id=order.id,
        container_kind="box",
        container_id=box.id,
        actor=actor,
    )
    for _ in range(2):
        await picking.manual_pick_product(s, tenant.id, supply.id, idempotency_key="pick", **args)
        await s.commit()
    options = await picking.get_pick_options(s, tenant.id, supply.id)
    source = next(
        row for row in options[0].locations if row.storage_location_id == location.id
    ).sources[0]
    assert not source.is_loose and source.picked == 1
    for _ in range(2):
        await picking.undo_pick(
            s, tenant.id, supply.id, order.id, idempotency_key="undo", actor=actor
        )
        await s.commit()
    assert await balances(s, product) == before
    await picking.manual_pick_product(s, tenant.id, supply.id, idempotency_key="re-pick", **args)
    await s.commit()
    assert sum((await balances(s, product)).values()) == 1
    await s.refresh(order)
    assert order.pack_status == "packed"


@pytest.mark.asyncio
async def test_mp_collection_cannot_spend_fbs_reservation_across_locations(
    db_session: AsyncSession,
):
    s = db_session
    tenant, seller, warehouse, product, order, supply, actor, location, _ = await seed(s)
    second = StorageLocation(tenant_id=tenant.id, warehouse_id=warehouse.id, code="B", barcode="B")
    s.add(second)
    await s.flush()
    s.add(
        InventoryBalance(
            tenant_id=tenant.id,
            product_id=product.id,
            storage_location_id=second.id,
            quantity=1,
            quantity_unpacked=1,
            quantity_packed=0,
        )
    )
    s.add(
        FbsOrderReservation(
            tenant_id=tenant.id,
            warehouse_id=warehouse.id,
            product_id=product.id,
            fbs_order_id=order.id,
            quantity=1,
        )
    )
    request = MarketplaceUnloadRequest(
        tenant_id=tenant.id,
        seller_id=seller.id,
        warehouse_id=warehouse.id,
        marketplace="wb",
        status="confirmed",
    )
    s.add(request)
    await s.flush()
    s.add(MarketplaceUnloadLine(request_id=request.id, product_id=product.id, quantity=2))
    await s.commit()
    options = await mp_pick.get_pick_options(s, tenant.id, request.id)
    assert [row.available for row in options[0].locations] == [1, 1]
    await collect.record_pick_allocation(
        s,
        tenant.id,
        request.id,
        storage_location_id=location.id,
        product_id=product.id,
        quantity=1,
        actor_user_id=actor.id,
    )
    await s.commit()
    options = await mp_pick.get_pick_options(s, tenant.id, request.id)
    assert all(row.available == 0 for row in options[0].locations)
    with pytest.raises(mp_pick.MarketplaceUnloadPickError, match="insufficient_available"):
        await collect.record_pick_allocation(
            s,
            tenant.id,
            request.id,
            storage_location_id=second.id,
            product_id=product.id,
            quantity=1,
            actor_user_id=actor.id,
        )
    await picking.manual_pick_product(
        s,
        tenant.id,
        supply.id,
        location_id=second.id,
        product_id=product.id,
        order_id=order.id,
        idempotency_key="own-reservation",
        actor=actor,
    )
    await s.commit()
    assert sum((await balances(s, product)).values()) == 1


@pytest.mark.asyncio
async def test_ozon_set_quantity_undo_targets_selected_box(db_session: AsyncSession):
    s = db_session
    tenant, _, warehouse, product, order, supply, actor, location, box = await seed(
        s, kind="box", marketplace="ozon"
    )
    assert box is not None
    position = await s.scalar(select(FbsOrderProduct).where(FbsOrderProduct.order_id == order.id))
    position.quantity = 2
    second_box = WarehouseBox(
        tenant_id=tenant.id,
        warehouse_id=warehouse.id,
        storage_location_id=location.id,
        internal_barcode="SECOND-BOX",
    )
    s.add(second_box)
    await s.flush()
    s.add(
        InventoryBalance(
            tenant_id=tenant.id,
            product_id=product.id,
            storage_location_id=location.id,
            container_kind="box",
            container_id=second_box.id,
            quantity=1,
            quantity_unpacked=1,
            quantity_packed=0,
        )
    )
    await s.commit()
    for container, qty, key in ((box, 1, "a"), (second_box, 1, "b"), (box, 0, "undo-a")):
        result = await picking.set_pick_quantity(
            s,
            tenant.id,
            supply.id,
            product_id=product.id,
            storage_location_id=location.id,
            quantity=qty,
            idempotency_key=key,
            actor=actor,
            container_kind="box",
            container_id=container.id,
        )
        await s.commit()
        assert result.quantity == qty
    remaining = await balances(s, product)
    assert remaining[(location.id, box.id)] == 1
    assert (location.id, second_box.id) not in remaining
    assert sum(remaining.values()) == 2
