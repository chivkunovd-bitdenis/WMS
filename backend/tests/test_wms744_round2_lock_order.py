"""WMS-744 second-round PostgreSQL lock-order contracts."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession
from test_ozon_posting_contract import _seed, posting_row
from test_wms744_inbound_product_lock_order import (
    BASE,
    _assert_successful_posts,
    _positive_balances,
    _seed_two_receipts,
)

from app.db.session import SessionLocal, engine
from app.models.fbs_order import FbsOrder, FbsOrderProductReservation
from app.models.fbs_warehouse_binding import FbsWarehouseBinding
from app.models.inventory_balance import InventoryBalance
from app.models.product import Product
from app.models.product_marketplace_link import ProductMarketplaceLink
from app.models.seller import Seller
from app.models.storage_location import StorageLocation
from app.models.warehouse import Warehouse
from app.services import inbound_intake_service as intake_svc
from app.services import inventory_service as inv_svc
from app.services import ozon_fbs_sync_service as sync_svc
from app.services.fbs_order_import_scope_service import FbsOrderImportStats, import_wb_order_rows
from app.services.marketplace_provider import FakeMarketplaceTransport, OzonMarketplaceProvider


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


@pytest.mark.asyncio
async def test_wms744_ozon_import_prelocks_all_orders_before_individual_reserves(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row locks are required")
    ctx = await _seed(db_session)
    second = Product(
        tenant_id=ctx.tenant.id, seller_id=ctx.seller.id,
        name="Second Ozon product", sku_code=f"wms744-{uuid.uuid4().hex}",
        fbs_stock_sync_enabled=True,
    )
    location = StorageLocation(
        tenant_id=ctx.tenant.id, warehouse_id=ctx.warehouse.id,
        code="W744", barcode=f"wms744-{uuid.uuid4().hex}",
    )
    db_session.add_all([second, location])
    await db_session.flush()
    db_session.add(ProductMarketplaceLink(
        tenant_id=ctx.tenant.id, seller_id=ctx.seller.id, product_id=second.id,
        marketplace="ozon", external_sku="5680762791",
        external_product_id="6204279712", external_offer_id="W744-SECOND",
    ))
    product_ids = {ctx.product.id, second.id}
    for product_id in product_ids:
        db_session.add(InventoryBalance(
            tenant_id=ctx.tenant.id, product_id=product_id,
            storage_location_id=location.id, quantity=10,
            quantity_unpacked=10, quantity_packed=0,
        ))
    await db_session.commit()
    rows = [posting_row(), posting_row(sku=5680762791)]
    rows[1]["posting_number"] = "W744-SECOND-1"
    rows[1]["products"][0]["offer_id"] = "W744-SECOND"
    # Import larger UUID first: row order must not set global stock-lock order.
    if str(ctx.product.id) < str(second.id):
        rows.reverse()
    events: list[tuple[str, set[uuid.UUID]]] = []
    sql_locks: list[str] = []
    original_batch = inv_svc.lock_stock_products
    original_single = inv_svc.lock_stock_product

    async def observe_batch(
        session: AsyncSession, tenant_id: uuid.UUID, ids: Iterable[uuid.UUID],
    ) -> None:
        ids = set(ids)
        await original_batch(session, tenant_id, ids)
        events.append(("batch", ids))

    async def observe_single(
        session: AsyncSession, tenant_id: uuid.UUID, product_id: uuid.UUID,
    ):
        events.append(("single", {product_id}))
        return await original_single(session, tenant_id, product_id)

    def observe_sql(_connection, _cursor, statement, _parameters, _context, _many):
        if "FROM products" in statement and "FOR UPDATE" in statement:
            sql_locks.append(statement)

    monkeypatch.setattr(inv_svc, "lock_stock_products", observe_batch)
    monkeypatch.setattr(inv_svc, "lock_stock_product", observe_single)
    event.listen(engine.sync_engine, "before_cursor_execute", observe_sql)
    try:
        result = await sync_svc.sync_ozon_orders(
            db_session, ctx.tenant.id, ctx.seller.id,
            OzonMarketplaceProvider(transport=FakeMarketplaceTransport(orders=rows)),
            AsyncMock(),
        )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", observe_sql)
    assert result["orders_created"] == 2
    assert events and events[0] == ("batch", product_ids), (
        f"All imported products must be prelocked before per-order locks: {events}"
    )
    assert sum(kind == "batch" for kind, _ids in events) == 1
    assert {next(iter(ids)) for kind, ids in events if kind == "single"} == product_ids
    assert sql_locks and "ORDER BY products.id" in sql_locks[0]
    orders = (await db_session.scalars(select(FbsOrder).where(
        FbsOrder.tenant_id == ctx.tenant.id, FbsOrder.marketplace == "ozon",
    ))).all()
    assert len(orders) == 2
    assert {order.reserve_status for order in orders} == {"reserved"}
    reservations = (await db_session.scalars(select(FbsOrderProductReservation).where(
        FbsOrderProductReservation.product_id.in_(product_ids),
    ))).all()
    assert len(reservations) == 2
    assert {(r.product_id, r.quantity) for r in reservations} == {
        (product_id, 2) for product_id in product_ids
    }
    balances = (await db_session.scalars(select(InventoryBalance).where(
        InventoryBalance.product_id.in_(product_ids),
    ))).all()
    assert len(balances) == 2
    assert {(b.product_id, b.quantity, b.quantity_unpacked, b.quantity_packed,
             b.storage_location_id) for b in balances} == {
        (product_id, 10, 10, 0, location.id) for product_id in product_ids
    }


@pytest.mark.asyncio
async def test_wms744_ozon_existing_supply_locks_packaging_before_stock_products(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row locks are required")
    from app.models.fbs_supply import FbsSupply
    from app.services import fbs_packaging_integration_service as packaging_svc

    ctx = await _seed(db_session)
    location = StorageLocation(
        tenant_id=ctx.tenant.id, warehouse_id=ctx.warehouse.id,
        code="W744-PARENT", barcode=f"w744-{uuid.uuid4().hex}",
    )
    db_session.add(location)
    await db_session.flush()
    db_session.add(InventoryBalance(
        tenant_id=ctx.tenant.id, product_id=ctx.product.id,
        storage_location_id=location.id, quantity=10,
        quantity_unpacked=10, quantity_packed=0,
    ))
    await db_session.commit()
    row = posting_row()
    await sync_svc.sync_ozon_orders(
        db_session, ctx.tenant.id, ctx.seller.id,
        OzonMarketplaceProvider(transport=FakeMarketplaceTransport(orders=[row])), AsyncMock(),
    )
    order = (await db_session.scalars(select(FbsOrder).where(
        FbsOrder.tenant_id == ctx.tenant.id,
        FbsOrder.external_order_id == row["posting_number"],
    ))).one()
    supply = FbsSupply(
        tenant_id=ctx.tenant.id, seller_id=ctx.seller.id,
        warehouse_id=ctx.warehouse.id, marketplace="ozon",
        name="WMS-744 parent lock contract", delivery_type="warehouse_sc",
    )
    db_session.add(supply)
    await db_session.flush()
    order.supply_id = supply.id
    await db_session.commit()
    order_before = (order.id, order.status, order.product_id, order.supply_id, order.reserve_status)
    reserves_before = {
        (r.id, r.order_product_id, r.product_id, r.quantity)
        for r in (await db_session.scalars(select(FbsOrderProductReservation).where(
            FbsOrderProductReservation.product_id == ctx.product.id,
        ))).all()
    }
    assert len(reserves_before) == 1
    lock_events: list[str] = []
    original_parent = packaging_svc.lock_order_batch_packaging_rows
    original_stock = inv_svc.lock_stock_products

    async def observe_parent(session, tenant_id, order_ids):
        await original_parent(session, tenant_id, order_ids)
        lock_events.append("packaging")

    async def observe_stock(session, tenant_id, product_ids):
        lock_events.append("products")
        await original_stock(session, tenant_id, product_ids)

    def observe_supply(_connection, _cursor, statement, _parameters, _context, _many):
        if "FROM fbs_supplies" in statement and "FOR UPDATE" in statement:
            lock_events.append("supply")

    monkeypatch.setattr(packaging_svc, "lock_order_batch_packaging_rows", observe_parent)
    monkeypatch.setattr(inv_svc, "lock_stock_products", observe_stock)
    event.listen(engine.sync_engine, "before_cursor_execute", observe_supply)
    try:
        await sync_svc.sync_ozon_orders(
            db_session, ctx.tenant.id, ctx.seller.id,
            OzonMarketplaceProvider(transport=FakeMarketplaceTransport(statuses=[row])),
            AsyncMock(), selected_posting_numbers=frozenset({row["posting_number"]}),
        )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", observe_supply)
    await db_session.refresh(order)
    assert (order.id, order.status, order.product_id, order.supply_id,
            order.reserve_status) == order_before
    reserves_after = {
        (r.id, r.order_product_id, r.product_id, r.quantity)
        for r in (await db_session.scalars(select(FbsOrderProductReservation).where(
            FbsOrderProductReservation.product_id == ctx.product.id,
        ))).all()
    }
    assert reserves_after == reserves_before
    balance = (await db_session.scalars(select(InventoryBalance).where(
        InventoryBalance.product_id == ctx.product.id,
    ))).one()
    assert (balance.quantity, balance.quantity_unpacked,
            balance.quantity_packed, balance.storage_location_id) == (10, 10, 0, location.id)
    assert "packaging" in lock_events and "supply" in lock_events and "products" in lock_events
    assert lock_events.index("packaging") < lock_events.index("products"), (
        f"Packaging parent rows must be locked before Product rows: {lock_events}"
    )
    assert lock_events.index("supply") < lock_events.index("products"), (
        f"Supply parent rows must be locked before Product rows: {lock_events}"
    )


@pytest.mark.asyncio
async def test_wms744_wb_recovered_saved_mapping_is_in_global_stock_prelock(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row locks are required")
    _headers, _request_ids, product_ids, _locations = await _seed_two_receipts(async_client)
    product_id = uuid.UUID(product_ids[0])
    now = datetime.now(UTC)
    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        assert product is not None
        tenant_id = product.tenant_id
        seller = Seller(tenant_id=tenant_id, name=f"W744 recovery {uuid.uuid4().hex[:8]}")
        warehouse = Warehouse(
            tenant_id=tenant_id, name="W744 recovery", code=f"w744-{uuid.uuid4().hex[:8]}",
        )
        session.add_all([seller, warehouse])
        await session.flush()
        product.seller_id = seller.id
        product.wb_barcode = f"W744-recover-{uuid.uuid4().hex}"
        product.wb_chrt_id = 744990
        session.add(FbsWarehouseBinding(
            tenant_id=tenant_id, seller_id=seller.id, marketplace="wb",
            wb_warehouse_id=744, wms_warehouse_id=warehouse.id,
            is_active=True, served=True,
        ))
        order = FbsOrder(
            tenant_id=tenant_id, seller_id=seller.id, warehouse_id=warehouse.id,
            product_id=None, marketplace="wb", wb_order_id=744990,
            wb_barcode=product.wb_barcode, wb_chrt_id=product.wb_chrt_id,
            created_at_wb=now, deadline_at=now + timedelta(days=1),
            mapping_status="missing", reserve_status="skipped_no_product",
        )
        session.add(order)
        await session.commit()
        seller_id, order_id = seller.id, order.id
    original_bulk = inv_svc.lock_stock_products
    original_single = inv_svc.lock_stock_product
    lock_events: list[tuple[str, set[uuid.UUID]]] = []

    async def observe_bulk(session, tenant_id, ids):
        ids = set(ids)
        lock_events.append(("bulk", ids))
        await original_bulk(session, tenant_id, ids)

    async def observe_single(session, tenant_id, pid):
        lock_events.append(("single", {pid}))
        return await original_single(session, tenant_id, pid)

    monkeypatch.setattr(inv_svc, "lock_stock_products", observe_bulk)
    monkeypatch.setattr(inv_svc, "lock_stock_product", observe_single)
    stats = FbsOrderImportStats()
    async with SessionLocal() as session:
        await import_wb_order_rows(session, tenant_id, seller_id, [{
            "id": 744990, "warehouseId": 744, "createdAt": now.isoformat(),
        }], stats)
        await session.commit()
        recovered = await session.get(FbsOrder, order_id)
        assert recovered is not None
        assert recovered.product_id == product_id
        assert recovered.mapping_status == "mapped"
    assert stats.upserted == 1 and stats.created == 0
    assert ("single", {product_id}) in lock_events
    assert lock_events[0] == ("bulk", {product_id}), (
        f"Recovered saved WB mapping must be in the global prelock: {lock_events}"
    )
