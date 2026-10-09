"""WMS-744 second-round PostgreSQL lock-order contracts."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from test_wms744_inbound_product_lock_order import (
    BASE,
    _assert_successful_posts,
    _positive_balances,
    _seed_two_receipts,
)

from app.db.session import SessionLocal, engine
from app.models.fbs_order import FbsOrder
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.product import Product
from app.models.seller import Seller
from app.models.warehouse import Warehouse
from app.services import inbound_intake_service as intake_svc
from app.services import inventory_service as inv_svc
from app.services.fbs_order_import_scope_service import FbsOrderImportStats, import_wb_order_rows


@pytest_asyncio.fixture(autouse=True)
async def _dispose_postgresql_pool_between_function_loops():
    yield
    if engine.dialect.name == "postgresql":
        await engine.dispose()


@pytest.mark.asyncio
async def test_wms744_parallel_reopen_receiving_locks_all_products_before_reversal(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row locks are required")

    headers, request_ids, product_ids, _locations = await _seed_two_receipts(async_client)
    for request_id in request_ids:
        completed = await async_client.post(
            f"{BASE}/{request_id}/complete-receiving", headers=headers
        )
        assert completed.status_code == 200, completed.text
        assert completed.json()["status"] == "sorting"

    ordered_products = sorted((uuid.UUID(product_id) for product_id in product_ids), key=str)
    request_order = {
        uuid.UUID(request_ids[0]): ordered_products,
        uuid.UUID(request_ids[1]): list(reversed(ordered_products)),
    }
    barrier = asyncio.Barrier(2)
    arrived: set[int] = set()
    original_get_request = intake_svc.get_request

    async def get_request_at_same_start(
        session: AsyncSession,
        tenant_id: uuid.UUID,
        request_id: uuid.UUID,
        **kwargs: Any,
    ):
        request = await original_get_request(session, tenant_id, request_id, **kwargs)
        order = request_order.get(request_id)
        if request is not None and kwargs.get("for_update") and order is not None:
            index = {product_id: position for position, product_id in enumerate(order)}
            request.lines.sort(key=lambda line: index[line.product_id])
            if id(session) not in arrived:
                arrived.add(id(session))
                await asyncio.wait_for(barrier.wait(), timeout=10)
        return request

    monkeypatch.setattr(intake_svc, "get_request", get_request_at_same_start)
    results = await asyncio.gather(
        *(
            async_client.post(f"{BASE}/{request_id}/reopen-receiving", headers=headers)
            for request_id in request_ids
        ),
        return_exceptions=True,
    )

    assert len(arrived) == 2, "The two HTTP requests must use separate database sessions"
    _assert_successful_posts(results)
    assert [result.json()["status"] for result in results if isinstance(result, Response)] == [
        "receiving",
        "receiving",
    ]
    assert await _positive_balances(product_ids) == {}


@pytest.mark.asyncio
async def test_wms744_parallel_distribution_completion_locks_all_products_before_putaway(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row locks are required")

    headers, request_ids, product_ids, locations = await _seed_two_receipts(async_client)
    box_ids: list[str] = []
    for request_id in request_ids:
        completed = await async_client.post(
            f"{BASE}/{request_id}/complete-receiving", headers=headers
        )
        assert completed.status_code == 200, completed.text
        request = await async_client.get(f"{BASE}/{request_id}", headers=headers)
        assert request.status_code == 200, request.text
        box_ids.append(request.json()["boxes"][0]["id"])

    ordered_products = sorted((uuid.UUID(product_id) for product_id in product_ids), key=str)
    request_order = {
        uuid.UUID(request_ids[0]): ordered_products,
        uuid.UUID(request_ids[1]): list(reversed(ordered_products)),
    }
    async with SessionLocal() as session:
        tenant_id = await session.scalar(
            select(Product.tenant_id).where(Product.id == ordered_products[0])
        )
    assert tenant_id is not None
    for request_id, box_id, location_id in zip(
        request_ids, box_ids, locations, strict=True
    ):
        order = request_order[uuid.UUID(request_id)]
        async with SessionLocal() as session:
            await intake_svc.replace_distribution_lines(
                session,
                tenant_id,
                uuid.UUID(request_id),
                lines=[
                    (uuid.UUID(box_id), product_id, uuid.UUID(location_id), 2)
                    for product_id in order
                ],
            )

    barrier = asyncio.Barrier(2)
    arrived: set[int] = set()
    original_distribution_posted_quantities = intake_svc._distribution_posted_quantities

    async def distribution_rows_at_same_start(
        session: AsyncSession,
        request,
        rows,
    ):
        order = request_order.get(request.id)
        if order is not None:
            index = {product_id: position for position, product_id in enumerate(order)}
            rows.sort(key=lambda row: index[row.product_id])
            if id(session) not in arrived:
                arrived.add(id(session))
                await asyncio.wait_for(barrier.wait(), timeout=10)
        return await original_distribution_posted_quantities(session, request, rows)

    monkeypatch.setattr(
        intake_svc,
        "_distribution_posted_quantities",
        distribution_rows_at_same_start,
    )
    results = await asyncio.gather(
        *(
            async_client.post(
                f"{BASE}/{request_id}/distribution-complete", headers=headers
            )
            for request_id in request_ids
        ),
        return_exceptions=True,
    )

    assert len(arrived) == 2, "The two HTTP requests must use separate database sessions"
    _assert_successful_posts(results)
    assert [result.json()["status"] for result in results if isinstance(result, Response)] == [
        "done",
        "done",
    ]
    balances = await _positive_balances(product_ids)
    assert balances == {
        (product_id, location_id): 2
        for product_id in product_ids
        for location_id in locations
    }


@pytest.mark.asyncio
async def test_wms744_wb_import_prelocks_all_products_in_stable_order(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row locks are required")

    _headers, _request_ids, product_ids, _locations = await _seed_two_receipts(async_client)
    products = sorted((uuid.UUID(product_id) for product_id in product_ids), key=str)
    now = datetime.now(UTC)
    async with SessionLocal() as session:
        tenant_id = await session.scalar(select(Product.tenant_id).where(Product.id == products[0]))
        assert tenant_id is not None
        seller = Seller(tenant_id=tenant_id, name=f"WMS-744 import {uuid.uuid4().hex[:8]}")
        warehouse = Warehouse(
            tenant_id=tenant_id,
            name="WMS-744 import warehouse",
            code=f"w744-import-{uuid.uuid4().hex[:8]}",
        )
        session.add_all([seller, warehouse])
        await session.flush()
        session.add(
            FbsWarehouseBinding(
                tenant_id=tenant_id,
                seller_id=seller.id,
                marketplace="wb",
                wb_warehouse_id=744,
                wms_warehouse_id=warehouse.id,
                is_active=True,
                served=True,
            )
        )
        orders: list[FbsOrder] = []
        for index, product_id in enumerate(products):
            product = await session.get(Product, product_id)
            assert product is not None
            product.seller_id = seller.id
            product.wb_barcode = f"W744-{uuid.uuid4().hex}"
            order = FbsOrder(
                tenant_id=tenant_id,
                seller_id=seller.id,
                warehouse_id=warehouse.id,
                product_id=product.id,
                marketplace="wb",
                wb_order_id=744000 + index,
                created_at_wb=now,
                deadline_at=now + timedelta(days=1),
                mapping_status="mapped",
                reserve_status="no_stock",
            )
            orders.append(order)
        session.add_all(orders)
        await session.commit()
        seller_id = seller.id

    original_bulk_lock = inv_svc.lock_stock_products
    original_single_lock = inv_svc.lock_stock_product
    lock_events: list[tuple[str, tuple[uuid.UUID, ...]]] = []

    async def observe_bulk_lock(
        session: AsyncSession,
        tenant_id: uuid.UUID,
        product_ids_to_lock,
    ) -> None:
        ordered = tuple(sorted(set(product_ids_to_lock), key=str))
        lock_events.append(("bulk", ordered))
        await original_bulk_lock(session, tenant_id, product_ids_to_lock)

    async def observe_single_lock(
        session: AsyncSession,
        tenant_id: uuid.UUID,
        product_id: uuid.UUID,
    ):
        lock_events.append(("single", (product_id,)))
        return await original_single_lock(session, tenant_id, product_id)

    monkeypatch.setattr(inv_svc, "lock_stock_products", observe_bulk_lock)
    monkeypatch.setattr(inv_svc, "lock_stock_product", observe_single_lock)
    rows: list[dict[str, Any]] = [
        {
            "id": int(order.wb_order_id),
            "warehouseId": 744,
            "createdAt": now.isoformat(),
        }
        for order in reversed(orders)
    ]
    stats = FbsOrderImportStats()
    async with SessionLocal() as session:
        await import_wb_order_rows(session, tenant_id, seller_id, rows, stats)
        await session.commit()

    assert stats.upserted == 2
    assert lock_events
    assert lock_events[0] == ("bulk", tuple(products)), (
        "The WB import must acquire every transaction product in one ordered batch "
        "before per-order reservation locks; observed "
        f"{lock_events}"
    )
