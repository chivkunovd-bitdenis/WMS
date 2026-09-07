"""WMS-392: packaging is a work fact, independent of warehouse operations."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrderProduct, FbsOrderProductReservation
from app.models.inventory_balance import InventoryBalance
from app.models.packaging_task import PackagingTask, PackagingTaskLine
from app.models.user import User
from app.services import fbs_packaging_integration_service as fbs_pack
from app.services import fbs_picking_service as picks
from app.services import packaging_task_service as packaging
from app.services.sorting_location_service import get_or_create_sorting_location
from tests.test_fbs_ozon_lane import _seed_ozon_supply_case
from tests.test_inventory_counts import _balance, _product, _tenant


async def stock_snapshot(session: AsyncSession) -> dict[str, list]:
    return {
        table: list((await session.execute(text(f"SELECT * FROM {table} ORDER BY id"))).all())
        for table in (
            "inventory_balances", "inventory_movements", "fbs_order_reservations",
            "fbs_order_product_reservations",
        )
    }


@pytest.mark.asyncio
async def test_manual_pack_scan_undo_and_confirm_leave_stock_untouched(
    async_client: AsyncClient,
) -> None:
    setup = await _tenant(async_client, "PackingFact")
    product_id = await _product(async_client, setup, name="Товар")
    await _balance(setup, product_id, 0)
    async with SessionLocal() as session:
        before = await stock_snapshot(session)
    response = await async_client.post(
        "/operations/packaging-tasks", headers=setup.headers,
        json={"warehouse_id": str(setup.warehouse_id), "lines": [{
            "product_id": str(product_id), "storage_location_id": str(setup.location_id),
            "quantity": 3,
        }]},
    )
    assert response.status_code == 201, response.text
    task = response.json()
    base = f"/operations/packaging-tasks/{task['id']}"
    line = task["lines"][0]
    for suffix, payload in (
        (f"/lines/{line['id']}/pack", {"quantity": 1}),
        ("/scan", {"barcode": line["sku_code"]}),
        ("/undo-last", None),
        (f"/lines/{line['id']}/mark-prepacked", {"quantity": 1}),
        (f"/lines/{line['id']}/confirm-packed", {"quantity": 1}),
        ("/complete", {"acknowledge_all_packed": False}),
        ("/complete", {"acknowledge_all_packed": False}),
    ):
        result = await async_client.post(base + suffix, headers=setup.headers, json=payload)
        assert result.status_code == 200, result.text
        async with SessionLocal() as session:
            assert await stock_snapshot(session) == before
    assert result.json()["status"] == "done"
    assert result.json()["lines"][0]["qty_done"] == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("on_hand", [0, 3])
async def test_ozon_single_repeat_and_mass_pack_are_facts_before_picking(
    db_session: AsyncSession, on_hand: int,
) -> None:
    tenant, _, warehouse, product, order, supply = await _seed_ozon_supply_case(
        db_session, packed=True,
    )
    assert supply is not None
    supply.status = "assembling"
    order.status = "assembling"
    order.pick_status = "pending"
    order.pack_status = "pending"
    if on_hand == 0:
        product.requires_honest_sign = True
        supply.honest_sign_skipped_at = datetime.now(UTC)
    position = FbsOrderProduct(
        order_id=order.id, product_id=product.id, ozon_sku=3001,
        quantity=2, position_index=0,
    )
    db_session.add(position)
    location = await get_or_create_sorting_location(db_session, tenant.id, warehouse.id)
    task = PackagingTask(tenant_id=tenant.id, warehouse_id=warehouse.id, status="draft")
    db_session.add(task)
    await db_session.flush()
    supply.packaging_task_id = task.id
    line = PackagingTaskLine(
        task_id=task.id, product_id=product.id, storage_location_id=location.id, qty_total=2,
    )
    db_session.add_all([
        line,
        InventoryBalance(
            tenant_id=tenant.id, product_id=product.id, storage_location_id=location.id,
            quantity=on_hand, quantity_unpacked=on_hand, quantity_packed=0,
        ),
        FbsOrderProductReservation(
            tenant_id=tenant.id, product_id=product.id, order_product_id=position.id,
            warehouse_id=warehouse.id, quantity=2,
        ),
    ])
    await db_session.commit()
    task = await packaging.get_task(db_session, tenant.id, task.id)
    assert task is not None
    line = task.lines[0]
    before = await stock_snapshot(db_session)
    for _ in range(2):
        await fbs_pack.record_fbs_pack_progress(
            db_session, tenant.id, task, line, 1, order_id=order.id,
            idempotency_key="same-unit",
        )
        await db_session.commit()
        assert line.qty_packed_in_task == 1
        assert await stock_snapshot(db_session) == before
    for _ in range(2):
        result = await packaging.pack_all_and_complete_fbs_task(
            db_session, tenant.id, task.id, acting_user_id=None,
        )
        assert result.task.status == "done"
        assert result.task.lines[0].qty_packed_in_task == 2
        assert await stock_snapshot(db_session) == before
    await db_session.refresh(order)
    assert order.pack_status == "packed"
    assert order.pick_status == "pending"
    if on_hand:
        actor = User(
            tenant_id=tenant.id, email="pack-pick@example.com",
            password_hash="unused-test-password", role="fulfillment_admin",
        )
        db_session.add(actor)
        await db_session.commit()
        await picks.manual_pick_product(
            db_session, tenant.id, supply.id, location_id=location.id, product_id=product.id,
            order_id=order.id, idempotency_key="pick-after-pack", actor=actor,
        )
        await db_session.commit()
        await picks.undo_pick(
            db_session, tenant.id, supply.id, order.id,
            idempotency_key="undo-after-pack", actor=actor,
        )
        await db_session.commit()
        await db_session.refresh(order)
        assert order.pack_status == "packed"
        assert order.pick_status == "pending"


@pytest.mark.asyncio
async def test_unload_marking_requirement_does_not_depend_on_packing_progress(
    db_session: AsyncSession,
) -> None:
    tenant, _, warehouse, product, _, _ = await _seed_ozon_supply_case(db_session, packed=True)
    from app.models.marketplace_unload import MarketplaceUnloadRequest
    request = MarketplaceUnloadRequest(
        tenant_id=tenant.id, warehouse_id=warehouse.id, marketplace="ozon", status="confirmed",
    )
    db_session.add(request)
    await db_session.flush()
    # A missing packaging task is not a shipment blocker.
    await packaging.assert_unload_marking_done(db_session, tenant.id, request.id)
    location = await get_or_create_sorting_location(db_session, tenant.id, warehouse.id)
    task = PackagingTask(
        tenant_id=tenant.id, warehouse_id=warehouse.id,
        marketplace_unload_request_id=request.id, status="draft",
    )
    db_session.add(task)
    await db_session.flush()
    line = PackagingTaskLine(
        task_id=task.id, product_id=product.id, storage_location_id=location.id, qty_total=2,
    )
    db_session.add(line)
    await db_session.commit()
    await packaging.assert_unload_marking_done(db_session, tenant.id, request.id)
    product.requires_honest_sign = True
    await db_session.commit()
    with pytest.raises(packaging.PackagingTaskServiceError, match="marking_not_done"):
        await packaging.assert_unload_marking_done(db_session, tenant.id, request.id)
    line.qty_marking_external = 2
    await db_session.commit()
    await packaging.assert_unload_marking_done(db_session, tenant.id, request.id)
    assert line.qty_packed_in_task == 0
