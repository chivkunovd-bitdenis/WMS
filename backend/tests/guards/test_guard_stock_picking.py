"""G-STOCK-2: source cell/container, undo and cancellation."""

import uuid

import pytest

from app.models.warehouse_box import WarehouseBox
from app.services import fbs_picking_service as picking
from app.services import inventory_service as inventory
from app.services.fbs_cancellation_service import _finish_local_cancellation
from tests.guards.stock_helpers import check, locations, moves, seed_fbs, total


@pytest.mark.asyncio
async def test_g_stock_2_pick_undo_and_cancel_restore_exact_source(db_session):
    """G-STOCK-2 · WMS-632 · решение владельца 02.10.2026: «Если отменим, вернётся назад»."""
    ctx, actor, orders = await seed_fbs(db_session)
    box = WarehouseBox(
        tenant_id=ctx.tenant.id,
        warehouse_id=ctx.supply_warehouse.id,
        storage_location_id=ctx.supply_address.id,
        container_kind="box",
        internal_barcode=f"BOX-{uuid.uuid4().hex}",
    )
    db_session.add(box)
    await db_session.flush()
    # A=3 loose units, B=2 boxed units; remaining 5 are already at sorting.
    await inventory.record_movement_and_adjust_balance(
        db_session,
        tenant_id=ctx.tenant.id,
        product_id=ctx.product.id,
        storage_location_id=ctx.supply_address.id,
        quantity_delta=-7,
        movement_type="stock_transfer_out",
        actor_user_id=actor.id,
    )
    for location, qty, extra in [
        (ctx.supply_address, 2, {"container_kind": "box", "container_id": box.id}),
        (ctx.supply_sorting, 5, {}),
    ]:
        await inventory.record_movement_and_adjust_balance(
            db_session,
            tenant_id=ctx.tenant.id,
            product_id=ctx.product.id,
            storage_location_id=location.id,
            quantity_delta=qty,
            movement_type="stock_transfer_in",
            actor_user_id=actor.id,
            **extra,
        )
    await db_session.commit()
    initial = await locations(db_session, ctx.product.id)
    for index, extra in enumerate([{}, {"container_kind": "box", "container_id": box.id}]):
        await picking.scan_pick_product(
            db_session,
            ctx.tenant.id,
            ctx.supply.id,
            location_id=ctx.supply_address.id,
            product_barcode=ctx.product.sku_code,
            product_id=ctx.product.id,
            order_id=orders[index].id,
            idempotency_key=f"pick-{index}",
            actor=actor,
            **extra,
        )
    check(await total(db_session, ctx.product.id), 10, "подбор сохраняет сумму склада")
    expected = dict(initial)
    expected[(str(ctx.supply_address.id), "None")] = 2
    expected[(str(ctx.supply_address.id), str(box.id))] = 1
    expected[(str(ctx.supply_sorting.id), "None")] = 7
    check(
        await locations(db_session, ctx.product.id),
        expected,
        "подбор переносит две штуки на сортировку",
    )
    for index in range(2):
        await picking.undo_pick(
            db_session,
            ctx.tenant.id,
            ctx.supply.id,
            orders[index].id,
            idempotency_key=f"undo-{index}",
            actor=actor,
        )
    check(
        await locations(db_session, ctx.product.id),
        initial,
        "отмена подбора возвращает ячейку и тару",
    )
    before = len(await moves(db_session, ctx.product.id))
    await picking.undo_pick(
        db_session,
        ctx.tenant.id,
        ctx.supply.id,
        orders[0].id,
        idempotency_key="undo-0",
        actor=actor,
    )
    check(len(await moves(db_session, ctx.product.id)), before, "повтор отмены не создаёт движения")
    await picking.scan_pick_product(
        db_session,
        ctx.tenant.id,
        ctx.supply.id,
        location_id=ctx.supply_address.id,
        product_barcode=ctx.product.sku_code,
        order_id=orders[0].id,
        idempotency_key="repick",
        actor=actor,
    )
    await _finish_local_cancellation(db_session, ctx.tenant.id, orders[0], actor_user_id=actor.id)
    restored = await locations(db_session, ctx.product.id)
    check(
        restored.get((str(ctx.supply_address.id), "None"), 0),
        3,
        "отмена заказа возвращает штуку в исходную ячейку",
    )
    check(
        await locations(db_session, ctx.product.id),
        initial,
        "отмена заказа возвращает подобранную штуку",
    )
    before = len(await moves(db_session, ctx.product.id))
    await _finish_local_cancellation(db_session, ctx.tenant.id, orders[0], actor_user_id=actor.id)
    check(
        len(await moves(db_session, ctx.product.id)),
        before,
        "повтор отмены заказа не возвращает вторую штуку",
    )
