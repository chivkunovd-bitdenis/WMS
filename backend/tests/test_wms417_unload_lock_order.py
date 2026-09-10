"""Actual PostgreSQL replay of opposite product order in the three unload paths."""

from __future__ import annotations

import asyncio
from datetime import date

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.marketplace_unload import MarketplaceUnloadLine, MarketplaceUnloadRequest
from app.models.marketplace_unload_reservation import MarketplaceUnloadReservation
from app.models.product import Product
from app.services import inventory_service
from app.services import marketplace_unload_service as unload
from tests.test_fbs_stock_rule_service import _seed


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["replace_lines", "plan_request", "confirm_request"])
async def test_opposite_product_order_waits_then_completes_without_deadlock(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    assert db_session.bind is not None
    if db_session.bind.dialect.name != "postgresql":
        pytest.skip("requires an isolated PostgreSQL WMS_TEST_DATABASE_URL")
    seed = await _seed(db_session, on_hand=10)
    second_product = Product(
        tenant_id=seed.tenant.id, seller_id=seed.seller.id, sku_code="other", name="Other"
    )
    db_session.add(second_product)
    await db_session.flush()
    location_id = await db_session.scalar(
        select(InventoryBalance.storage_location_id).where(
            InventoryBalance.product_id == seed.product.id,
        )
    )
    db_session.add(
        InventoryBalance(
            tenant_id=seed.tenant.id,
            product_id=second_product.id,
            storage_location_id=location_id,
            quantity=10,
            quantity_unpacked=10,
        )
    )
    product_ids = sorted([seed.product.id, second_product.id], key=str)
    requests = [
        MarketplaceUnloadRequest(
            tenant_id=seed.tenant.id,
            seller_id=seed.seller.id,
            warehouse_id=seed.warehouse.id,
            marketplace="ozon",
            status="draft",
            planned_shipment_date=date(2026, 9, 11),
        )
        for _ in range(2)
    ]
    db_session.add_all(requests)
    await db_session.flush()
    for index, request in enumerate(requests):
        for pid in list(reversed(product_ids)) if index == 0 else product_ids:
            db_session.add(MarketplaceUnloadLine(request_id=request.id, product_id=pid, quantity=1))
    await db_session.commit()
    request_ids = [request.id for request in requests]
    first_locked, release_first, second_started = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original_lock, original_get = inventory_service.lock_stock_product, unload.get_request
    attempts: dict[int, list] = {0: [], 1: []}
    backend_pids: dict[int, int] = {}

    async def ordered_request(session, tenant_id, request_id):
        request = await original_get(session, tenant_id, request_id)
        if request is not None and "writer" in session.info:
            # SQL relationship order has no guarantee; replay both possible orders.
            request.lines.sort(
                key=lambda ln: str(ln.product_id), reverse=session.info["writer"] == 0
            )
        return request

    async def observed_lock(session, tenant_id, product_id):
        index = session.info.get("writer")
        if index is not None:
            attempts[index].append(product_id)
        result = await original_lock(session, tenant_id, product_id)
        if index == 0 and len(attempts[index]) == 1:
            first_locked.set()
            await asyncio.wait_for(release_first.wait(), 10)
        return result

    monkeypatch.setattr(unload, "get_request", ordered_request)
    monkeypatch.setattr(inventory_service, "lock_stock_product", observed_lock)

    async def writer(index: int) -> None:
        async with AsyncSession(bind=db_session.bind, expire_on_commit=False) as session:
            session.info["writer"] = index
            backend_pids[index] = int(await session.scalar(text("select pg_backend_pid()")))
            if index == 1:
                second_started.set()
            if operation == "replace_lines":
                ordered = list(reversed(product_ids)) if index == 0 else product_ids
                await unload.replace_lines(
                    session, seed.tenant.id, request_ids[index], lines=[(pid, 1) for pid in ordered]
                )
            else:
                await getattr(unload, operation)(session, seed.tenant.id, request_ids[index])

    first = asyncio.create_task(writer(0))
    second = None
    try:
        await asyncio.wait_for(first_locked.wait(), 10)
        second = asyncio.create_task(writer(1))
        await asyncio.wait_for(second_started.wait(), 10)
        blocked = False
        for _ in range(200):
            blocked = bool(
                await db_session.scalar(
                    text("select :first = any(pg_blocking_pids(:second))"),
                    {"first": backend_pids[0], "second": backend_pids[1]},
                )
            )
            if blocked:
                break
            await asyncio.sleep(0.01)
        assert blocked, "no real PostgreSQL row-lock wait observed"
        assert attempts[0][0] == attempts[1][0] == product_ids[0]
    finally:
        release_first.set()
        await asyncio.wait_for(asyncio.gather(first, *([second] if second else [])), 10)
    assert attempts[0][:2] == attempts[1][:2] == product_ids
    statuses = (
        await db_session.scalars(
            select(MarketplaceUnloadRequest.status).where(
                MarketplaceUnloadRequest.id.in_(request_ids),
            )
        )
    ).all()
    expected = {
        "replace_lines": "draft",
        "plan_request": "submitted",
        "confirm_request": "confirmed",
    }
    assert statuses == [expected[operation]] * 2
    assert await db_session.scalar(select(func.count()).select_from(MarketplaceUnloadLine)) == 4
    reserves = (
        await db_session.execute(
            select(
                MarketplaceUnloadReservation.product_id,
                func.sum(MarketplaceUnloadReservation.quantity),
            ).group_by(MarketplaceUnloadReservation.product_id)
        )
    ).all()
    assert dict(reserves) == ({} if operation == "replace_lines" else dict.fromkeys(product_ids, 2))
    assert await db_session.scalar(select(func.sum(InventoryBalance.quantity))) == 20
    assert await db_session.scalar(select(func.count()).select_from(InventoryMovement)) == 0
