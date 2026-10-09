"""WMS-744: concurrent full FBO shipments must use one product lock order."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterable

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession
from test_wms744_inbound_product_lock_order import _positive_balances, _seed_two_receipts

from app.db.session import engine
from app.services import inventory_service as inv_svc
from app.services import outbound_shipment_service as outbound_svc

BASE = "/operations/outbound-shipment-requests"


@pytest_asyncio.fixture(autouse=True)
async def _dispose_postgresql_pool_between_function_loops():
    yield
    if engine.dialect.name == "postgresql":
        await engine.dispose()


@pytest.mark.asyncio
async def test_wms744_simultaneous_outbound_posts_lock_shared_products_without_deadlock(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row locks are required")

    headers, receiving_ids, product_ids, _locations = await _seed_two_receipts(async_client)
    for receiving_id in receiving_ids:
        completed = await async_client.post(
            f"/operations/inbound-intake-requests/{receiving_id}/complete-receiving",
            headers=headers,
        )
        assert completed.status_code == 200, completed.text
    balances_before = await _positive_balances(product_ids)
    assert len(balances_before) == 2
    assert set(balances_before.values()) == {4}
    location_id = next(iter(balances_before))[1]
    receipt = await async_client.get(
        f"/operations/inbound-intake-requests/{receiving_ids[0]}", headers=headers
    )
    assert receipt.status_code == 200, receipt.text
    request_order: dict[uuid.UUID, list[uuid.UUID]] = {}
    for order in (product_ids, list(reversed(product_ids))):
        created = await async_client.post(
            BASE, headers=headers, json={"warehouse_id": receipt.json()["warehouse_id"]}
        )
        assert created.status_code == 201, created.text
        request_id = created.json()["id"]
        request_order[uuid.UUID(request_id)] = [uuid.UUID(pid) for pid in order]
        for product_id in order:
            line = await async_client.post(
                f"{BASE}/{request_id}/lines",
                headers=headers,
                json={
                    "product_id": product_id,
                    "quantity": 1,
                    "storage_location_id": location_id,
                },
            )
            assert line.status_code == 201, line.text
        submitted = await async_client.post(f"{BASE}/{request_id}/submit", headers=headers)
        assert submitted.status_code == 200, submitted.text

    original_get = outbound_svc.get_request
    original_single_lock = inv_svc.lock_stock_product
    original_bulk_lock = inv_svc.lock_stock_products
    barrier = asyncio.Barrier(2)
    first_single_locks: set[int] = set()
    operation_sessions: set[int] = set()
    ordered_prelocks: set[int] = set()

    async def get_with_opposite_line_order(
        session: AsyncSession, tenant_id: uuid.UUID, request_id: uuid.UUID, **kwargs: object
    ):
        request = await original_get(session, tenant_id, request_id, **kwargs)
        if request is not None and request_id in request_order:
            operation_sessions.add(id(session))
            index = {pid: i for i, pid in enumerate(request_order[request_id])}
            request.lines.sort(key=lambda line: index[line.product_id])
        return request

    async def observe_prelock(
        session: AsyncSession, tenant_id: uuid.UUID, ids: Iterable[uuid.UUID]
    ) -> None:
        await original_bulk_lock(session, tenant_id, ids)
        ordered_prelocks.add(id(session))

    async def synchronize_first_product_lock(
        session: AsyncSession, tenant_id: uuid.UUID, product_id: uuid.UUID
    ):
        product = await original_single_lock(session, tenant_id, product_id)
        # Before the fix each transaction holds its own first product. The
        # barrier then sends both to the other's product: a real PG wait cycle.
        # Completed bulk prelocking already serializes transactions, so the
        # barrier must not manufacture a hang after all products are locked.
        if id(session) not in ordered_prelocks and id(session) not in first_single_locks:
            first_single_locks.add(id(session))
            await asyncio.wait_for(barrier.wait(), timeout=10)
        return product

    monkeypatch.setattr(outbound_svc, "get_request", get_with_opposite_line_order)
    monkeypatch.setattr(inv_svc, "lock_stock_products", observe_prelock)
    monkeypatch.setattr(inv_svc, "lock_stock_product", synchronize_first_product_lock)
    results = await asyncio.gather(
        *(
            async_client.post(f"{BASE}/{request_id}/post", headers=headers)
            for request_id in request_order
        ),
        return_exceptions=True,
    )
    assert len(operation_sessions) == 2, "The posts must use separate database sessions"
    failures = [
        f"{type(result).__name__}: {result}"
        if isinstance(result, BaseException)
        else f"HTTP {result.status_code}: {result.text}"
        for result in results
        if isinstance(result, BaseException) or result.status_code != 200
    ]
    assert not failures, "Concurrent outbound post failed: " + "; ".join(failures)
    for result in results:
        assert isinstance(result, Response)
        assert result.json()["status"] == "posted"
        assert len(result.json()["lines"]) == 2
        assert all(line["shipped_qty"] == 1 for line in result.json()["lines"])
    assert await _positive_balances(product_ids) == {
        key: quantity - 2 for key, quantity in balances_before.items()
    }
