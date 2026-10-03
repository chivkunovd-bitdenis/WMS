"""G-STOCK-6: printing recovery and KIZ clearing preserve stock and picking."""

import uuid
from unittest.mock import AsyncMock

import fitz
import httpx
import pytest
from sqlalchemy import select

from app.models.fbs_order import FbsOrder
from app.models.fbs_order_pick import FbsOrderPick
from app.services import fbs_kiz_service as kiz
from app.services import fbs_marking_service as marking
from app.services import fbs_picking_service as picking
from app.services import fbs_print_job_service as printing
from app.services.inventory_service import update_fbs_order_reservation
from tests.guards.stock_helpers import check, locations, reserved, seed_fbs, total


@pytest.mark.asyncio
async def test_g_stock_6_print_reprint_failure_recovery_and_clear_kiz(db_session, monkeypatch):
    """G-STOCK-6 · WMS-632 · решение владельца 02.10.2026:
    «только в этом случае мы списываем остаток».
    """
    ctx, actor, orders = await seed_fbs(db_session, count=1)
    tenant_id, supply_id, product_id = ctx.tenant.id, ctx.supply.id, ctx.product.id
    warehouse_id, actor_id, order_id = ctx.supply_warehouse.id, actor.id, orders[0].id
    await update_fbs_order_reservation(db_session, orders[0], reserve=True)
    await picking.scan_pick_product(
        db_session,
        tenant_id,
        supply_id,
        location_id=ctx.supply_address.id,
        product_barcode=ctx.product.sku_code,
        idempotency_key="guard-print-pick",
        actor=actor,
    )
    orders[0].meta_details_json = {"sgtin": {"value": "010460000000001121TEST"}}
    await db_session.commit()

    async def snapshot():
        picks = list(
            await db_session.execute(
                select(
                    FbsOrderPick.id, FbsOrderPick.undone_at, FbsOrderPick.source_storage_location_id
                ).where(FbsOrderPick.fbs_order_id == order_id)
            )
        )
        return (
            await total(db_session, product_id),
            await reserved(db_session, product_id),
            await locations(db_session, product_id),
            [tuple(row) for row in picks],
        )

    before = await snapshot()
    with fitz.open() as pdf:
        pdf.new_page(width=164, height=113).insert_text((10, 20), "G-STOCK-6")
        document = pdf.tobytes()
    first = await printing.create_document_print_job(
        db_session,
        tenant_id,
        job_id=uuid.uuid4(),
        supply_id=supply_id,
        document=document,
        user_id=actor_id,
    )
    await db_session.commit()
    asset_id = uuid.UUID(first.payload_json["asset_id"])
    # Explicit reprint and safe retry reuse the immutable, already stored asset.
    for stage, succeeds in [
        ("печать", True),
        ("перепечать", True),
        ("сбой печати", False),
        ("восстановление", True),
    ]:
        job = (
            first
            if stage == "печать"
            else await printing.create_print_job(
                db_session,
                tenant_id,
                job_id=uuid.uuid4(),
                asset_id=asset_id,
                warehouse_id=warehouse_id,
                user_id=actor_id,
            )
        )
        await db_session.commit()
        await printing.claim_next_print_job(db_session, tenant_id, warehouse_id=warehouse_id)
        await printing.load_print_job_content(
            db_session, tenant_id, job.id, warehouse_id=warehouse_id
        )
        await printing.finish_print_job(
            db_session,
            tenant_id,
            job.id,
            warehouse_id=warehouse_id,
            queue_receipt=str(job.id) if succeeds else None,
            handed_to_queue=succeeds,
            error_message=None if succeeds else "printer offline before queue",
        )
        await db_session.commit()
        check(await snapshot(), before, f"{stage} сохраняет остаток, резерв и подбор")
    monkeypatch.setattr(marking, "require_marketplace_token", AsyncMock(return_value="test-token"))
    monkeypatch.setattr(kiz, "delete_marketplace_order_meta", AsyncMock(return_value=None))
    async with httpx.AsyncClient() as client:
        await kiz.cancel_order_kiz(db_session, tenant_id, actor_id, order_id, client)
    # WMS-609: require the operation to really clear the saved code, so an
    # ineffective cleanup cannot pass merely because stock stayed unchanged.
    saved_meta = await db_session.scalar(
        select(FbsOrder.meta_details_json).where(FbsOrder.id == order_id)
    )
    check(
        (saved_meta or {}).get("sgtin"),
        None,
        "очистка КИЗ действительно удаляет сохранённый sgtin (WMS-609)",
    )
    check(await reserved(db_session, product_id), before[1], "очистка КИЗ не снимает резерв заказа")
    check(await snapshot(), before, "очистка КИЗ сохраняет остаток, резерв и подбор")
