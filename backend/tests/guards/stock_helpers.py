"""Shared stock observations and protected fixture construction."""

import uuid

from sqlalchemy import func, select

from app.models.fbs_order import FbsOrderReservation
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.product_barcode import ProductBarcode
from app.models.user import User
from app.services import inventory_service as inventory
from tests.guards.stock_seeds import _order, _seed_context


def check(actual, expected, rule):
    assert actual == expected, (
        f"нарушено решение владельца от 02.10: {rule}, было {expected}, стало {actual}"
    )


async def total(session, product_id):
    return int(
        await session.scalar(
            select(func.coalesce(func.sum(InventoryBalance.quantity), 0)).where(
                InventoryBalance.product_id == product_id
            )
        )
        or 0
    )


async def locations(session, product_id):
    rows = await session.execute(
        select(
            InventoryBalance.storage_location_id,
            InventoryBalance.container_id,
            InventoryBalance.quantity,
        ).where(InventoryBalance.product_id == product_id)
    )
    return {(str(loc), str(box)): int(qty) for loc, box, qty in rows if qty}


async def reserved(session, product_id):
    return int(
        await session.scalar(
            select(func.coalesce(func.sum(FbsOrderReservation.quantity), 0)).where(
                FbsOrderReservation.product_id == product_id
            )
        )
        or 0
    )


async def moves(session, product_id, kind=None):
    stmt = select(InventoryMovement).where(InventoryMovement.product_id == product_id)
    if kind:
        stmt = stmt.where(InventoryMovement.movement_type == kind)
    return list((await session.scalars(stmt)).all())


async def seed_fbs(session, *, stock=10, count=3):
    ctx = await _seed_context(session)
    actor = User(
        tenant_id=ctx.tenant.id,
        email=f"guard-{uuid.uuid4().hex}@example.test",
        password_hash="unused",
        role="fulfillment_admin",
    )
    session.add(actor)
    session.add(
        ProductBarcode(
            tenant_id=ctx.tenant.id,
            seller_id=ctx.seller.id,
            product_id=ctx.product.id,
            barcode=ctx.product.sku_code,
        )
    )
    orders = [_order(ctx, wb_order_id=700001 + index) for index in range(count)]
    for order in orders:
        order.wb_barcode = ctx.product.sku_code
        order.wb_supply_id = ctx.supply.wb_supply_id
    session.add_all(orders)
    await session.flush()
    await inventory.record_movement_and_adjust_balance(
        session,
        tenant_id=ctx.tenant.id,
        product_id=ctx.product.id,
        storage_location_id=ctx.supply_address.id,
        quantity_delta=stock,
        movement_type="inbound_intake",
        actor_user_id=actor.id,
    )
    await session.commit()
    return ctx, actor, orders
