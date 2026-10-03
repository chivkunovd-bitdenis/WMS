"""G-STOCK-1: posted documents versus FBO staging."""

import pytest

from app.services import inventory_service as inventory
from app.services import marketplace_unload_collect_service as collect
from app.services import marketplace_unload_service as unload
from tests.guards.stock_helpers import check, moves, total
from tests.guards.stock_seeds import _fixture


@pytest.mark.asyncio
async def test_g_stock_1_documents_and_fbo_staging(db_session):
    """G-STOCK-1 · WMS-632 · решение владельца 02.10.2026:
    «только в этом случае мы списываем остаток».
    """
    ctx = await _fixture(db_session, stock=10, plan=3)
    for delta, kind, expected in [(3, "inbound_intake", 13), (-2, "inventory_count", 11)]:
        await inventory.record_movement_and_adjust_balance(
            db_session,
            tenant_id=ctx.tenant.id,
            product_id=ctx.product.id,
            storage_location_id=ctx.location.id,
            quantity_delta=delta,
            movement_type=kind,
            actor_user_id=ctx.actor.id,
        )
        check(await total(db_session, ctx.product.id), expected, f"проведение {kind}")
    await inventory.transfer_on_hand_between_locations(
        db_session,
        ctx.tenant.id,
        from_storage_location_id=ctx.location.id,
        to_storage_location_id=ctx.sorting.id,
        product_id=ctx.product.id,
        quantity=3,
        actor_user_id=ctx.actor.id,
    )
    check(await total(db_session, ctx.product.id), 11, "перемещение сохраняет остаток")
    await collect.collect_into_box(
        db_session,
        ctx.tenant.id,
        ctx.request.id,
        box_id=ctx.box.id,
        storage_location_id=ctx.sorting.id,
        product_id=ctx.product.id,
        quantity=3,
        actor_user_id=ctx.actor.id,
    )
    check(await total(db_session, ctx.product.id), 11, "укладка FBO не списывает товар")
    check(
        len(await moves(db_session, ctx.product.id, "marketplace_unload")),
        0,
        "до проведения FBO нет расходных движений",
    )
    await db_session.commit()
    await db_session.refresh(ctx.box, ["lines"])
    await db_session.refresh(ctx.request, ["boxes"])
    await unload.complete_unload(
        db_session,
        ctx.tenant.id,
        ctx.request.id,
        acknowledge_discrepancy=True,
        performer_id=ctx.actor.id,
    )
    check(await total(db_session, ctx.product.id), 8, "проведение FBO списывает ровно факт 3")
