from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from app.models.inventory_balance import InventoryBalance
from app.models.marketplace_unload import (
    MarketplaceUnloadBox,
    MarketplaceUnloadBoxLine,
    MarketplaceUnloadLine,
    MarketplaceUnloadPickAllocation,
    MarketplaceUnloadRequest,
)
from app.models.packaging_task import PackagingTask, PackagingTaskLine
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.tenant import Tenant
from app.models.user import User
from app.models.warehouse import Warehouse
from app.services import marketplace_unload_collect_service as collect_svc
from app.services import packaging_task_service as pkg_svc


async def _historical_fixture(db_session, *, fresh_unpacked: int):
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant(name="WMS-444", slug=f"wms444-history-{suffix}")
    db_session.add(tenant)
    await db_session.flush()
    warehouse = Warehouse(tenant_id=tenant.id, name="WMS-444", code=f"w444h-{suffix}")
    seller = Seller(tenant_id=tenant.id, name="WMS-444 seller")
    actor = User(
        tenant_id=tenant.id,
        email=f"wms444-history-{suffix}@example.test",
        password_hash="synthetic-unused",
        role="fulfillment_staff",
        packaging_rate_kopecks=700,
    )
    db_session.add_all((warehouse, seller, actor))
    await db_session.flush()
    product = Product(
        tenant_id=tenant.id,
        seller_id=seller.id,
        name="WMS-444 product",
        sku_code=f"wms444-history-{suffix}",
    )
    location = StorageLocation(
        tenant_id=tenant.id,
        warehouse_id=warehouse.id,
        code=f"W444H-{suffix}",
        barcode=f"W444H-{suffix}",
    )
    request = MarketplaceUnloadRequest(
        tenant_id=tenant.id,
        warehouse_id=warehouse.id,
        seller_id=seller.id,
        marketplace="wb",
        status="collecting",
    )
    db_session.add_all((product, location, request))
    await db_session.flush()
    db_session.add_all(
        (
            InventoryBalance(
                tenant_id=tenant.id,
                product_id=product.id,
                storage_location_id=location.id,
                quantity=fresh_unpacked,
                quantity_unpacked=fresh_unpacked,
                quantity_packed=0,
            ),
            MarketplaceUnloadLine(request_id=request.id, product_id=product.id, quantity=3),
        )
    )
    task = PackagingTask(
        tenant_id=tenant.id,
        warehouse_id=warehouse.id,
        marketplace_unload_request_id=request.id,
        status="draft",
    )
    box = MarketplaceUnloadBox(request_id=request.id, box_preset="60_40_40")
    db_session.add_all((task, box))
    await db_session.flush()
    task_line = PackagingTaskLine(
        task_id=task.id,
        product_id=product.id,
        storage_location_id=location.id,
        qty_total=3,
        qty_suggested_packed=3,
        qty_confirmed_packed=1,
        qty_packed_in_task=1,
    )
    historical_box = MarketplaceUnloadBoxLine(
        box_id=box.id,
        product_id=product.id,
        quantity=2,
    )
    historical_allocation = MarketplaceUnloadPickAllocation(
        request_id=request.id,
        product_id=product.id,
        storage_location_id=location.id,
        quantity=2,
    )
    db_session.add_all((task_line, historical_box, historical_allocation))
    await db_session.commit()
    return (
        tenant,
        warehouse,
        actor,
        product,
        location,
        request,
        task,
        task_line,
        box,
        historical_box,
    )


async def _task_line(db_session, tenant_id, task_id) -> PackagingTaskLine:
    task = await pkg_svc.get_task(db_session, tenant_id, task_id)
    assert task is not None
    assert len(task.lines) == 1
    return task.lines[0]


@pytest.mark.asyncio
async def test_historical_partial_removal_preserves_ready_then_bills_new_work(db_session) -> None:
    (
        tenant,
        _warehouse,
        actor,
        product,
        location,
        request,
        task,
        _task_line_before,
        box,
        historical_box,
    ) = await _historical_fixture(db_session, fresh_unpacked=1)

    await collect_svc.collect_into_box(
        db_session,
        tenant.id,
        request.id,
        box_id=box.id,
        storage_location_id=location.id,
        product_id=product.id,
        quantity=1,
        actor_user_id=actor.id,
    )
    await collect_svc.remove_from_box(
        db_session,
        tenant.id,
        request.id,
        box_id=box.id,
        line_id=historical_box.id,
        quantity=1,
        actor_user_id=actor.id,
    )

    line = await _task_line(db_session, tenant.id, task.id)
    assert (line.qty_confirmed_packed, line.qty_packed_in_task) == (1, 1)
    assert (line.qty_legacy_confirmed_packed, line.qty_legacy_packed_in_task) == (1, 0)
    box_line = await db_session.get(MarketplaceUnloadBoxLine, historical_box.id)
    allocation = (
        await db_session.execute(
            select(MarketplaceUnloadPickAllocation).where(
                MarketplaceUnloadPickAllocation.request_id == request.id
            )
        )
    ).scalar_one()
    assert box_line is not None
    assert (
        box_line.quantity,
        box_line.quantity_source_known,
        box_line.quantity_packed,
    ) == (2, 1, 0)
    assert (allocation.quantity, allocation.quantity_source_known, allocation.quantity_packed) == (
        2,
        1,
        0,
    )
    balance = (
        await db_session.execute(
            select(
                func.sum(InventoryBalance.quantity),
                func.sum(InventoryBalance.quantity_packed),
            ).where(InventoryBalance.product_id == product.id)
        )
    ).one()
    assert tuple(map(int, balance)) == (1, 0)

    completed = await pkg_svc.complete_task(
        db_session, tenant.id, task.id, acting_user_id=actor.id
    )
    assert (completed.billing_units_packed, completed.billing_earned_kopecks) == (1, 700)


@pytest.mark.asyncio
async def test_historical_removal_to_zero_does_not_revive_on_recollect(db_session) -> None:
    (
        tenant,
        warehouse,
        actor,
        product,
        location,
        request,
        task,
        _task_line_before,
        box,
        historical_box,
    ) = await _historical_fixture(db_session, fresh_unpacked=0)

    await collect_svc.remove_from_box(
        db_session,
        tenant.id,
        request.id,
        box_id=box.id,
        line_id=historical_box.id,
        quantity=1,
        actor_user_id=actor.id,
    )
    line = await _task_line(db_session, tenant.id, task.id)
    assert (line.qty_confirmed_packed, line.qty_packed_in_task) == (1, 0)
    assert (line.qty_legacy_confirmed_packed, line.qty_legacy_packed_in_task) == (1, 0)

    await collect_svc.remove_from_box(
        db_session,
        tenant.id,
        request.id,
        box_id=box.id,
        line_id=historical_box.id,
        quantity=1,
        actor_user_id=actor.id,
    )
    line = await _task_line(db_session, tenant.id, task.id)
    assert (line.qty_confirmed_packed, line.qty_packed_in_task) == (0, 0)
    assert (line.qty_legacy_confirmed_packed, line.qty_legacy_packed_in_task) == (0, 0)

    await collect_svc.collect_into_box(
        db_session,
        tenant.id,
        request.id,
        box_id=box.id,
        storage_location_id=location.id,
        product_id=product.id,
        quantity=1,
        actor_user_id=actor.id,
    )
    task_for_sync = await pkg_svc.get_task(db_session, tenant.id, task.id)
    assert task_for_sync is not None
    await pkg_svc.sync_mp_task_packed_from_boxes(db_session, tenant.id, task_for_sync)
    line = await _task_line(db_session, tenant.id, task.id)
    assert (line.qty_confirmed_packed, line.qty_packed_in_task) == (0, 1)
    await collect_svc.rollback_all_collected_for_cancel(
        db_session,
        tenant.id,
        warehouse.id,
        request.id,
        actor_user_id=actor.id,
    )
    await db_session.commit()
    balance = (
        await db_session.execute(
            select(
                func.sum(InventoryBalance.quantity),
                func.sum(InventoryBalance.quantity_packed),
            ).where(InventoryBalance.product_id == product.id)
        )
    ).one()
    assert tuple(map(int, balance)) == (2, 0)
    remaining_allocations = (
        await db_session.execute(
            select(func.count()).select_from(MarketplaceUnloadPickAllocation).where(
                MarketplaceUnloadPickAllocation.request_id == request.id
            )
        )
    ).scalar_one()
    assert remaining_allocations == 0
