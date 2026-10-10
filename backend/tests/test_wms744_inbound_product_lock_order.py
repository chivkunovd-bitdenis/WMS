"""WMS-744: independent inbound documents lock shared products in one order."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response
from inbound_box_intake_helpers import post_primary_accept
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal, engine
from app.models.inventory_balance import InventoryBalance
from app.services import inbound_intake_service as intake_svc

BASE = "/operations/inbound-intake-requests"
QUANTITY_PER_PRODUCT = 2


@pytest_asyncio.fixture(autouse=True)
async def _dispose_postgresql_pool_between_function_loops():
    yield
    if engine.dialect.name == "postgresql":
        await engine.dispose()


async def _seed_two_receipts(
    client: AsyncClient,
) -> tuple[dict[str, str], list[str], list[str], list[str]]:
    suffix = uuid.uuid4().hex[:10]
    registration = await client.post(
        "/auth/register",
        json={
            "organization_name": f"WMS-744 {suffix}",
            "slug": f"wms744-{suffix}",
            "admin_email": f"wms744-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registration.status_code == 200, registration.text
    headers = {"Authorization": f"Bearer {registration.json()['access_token']}"}

    warehouse = await client.post(
        "/warehouses",
        headers=headers,
        json={"name": "WMS-744", "code": f"W744-{suffix}"},
    )
    assert warehouse.status_code == 200, warehouse.text
    warehouse_id = warehouse.json()["id"]
    locations: list[str] = []
    for code in ("W744-A", "W744-B"):
        location = await client.post(
            f"/warehouses/{warehouse_id}/locations",
            headers=headers,
            json={"code": f"{code}-{suffix}"},
        )
        assert location.status_code == 200, location.text
        locations.append(location.json()["id"])

    product_ids: list[str] = []
    for index in range(2):
        product = await client.post(
            "/products",
            headers=headers,
            json={
                "name": f"WMS-744 shared product {index}",
                "sku_code": f"W744-{suffix}-{index}",
                "length_mm": 1,
                "width_mm": 1,
                "height_mm": 1,
            },
        )
        assert product.status_code == 200, product.text
        product_ids.append(product.json()["id"])

    request_ids: list[str] = []
    orders = (product_ids, list(reversed(product_ids)))
    for order in orders:
        created = await client.post(
            BASE, headers=headers, json={"warehouse_id": warehouse_id}
        )
        assert created.status_code == 201, created.text
        request_id = created.json()["id"]
        request_ids.append(request_id)
        for product_id in order:
            line = await client.post(
                f"{BASE}/{request_id}/lines",
                headers=headers,
                json={"product_id": product_id, "expected_qty": QUANTITY_PER_PRODUCT},
            )
            assert line.status_code == 201, line.text

        receiving = await post_primary_accept(
            client, BASE, request_id, headers, create_boxes=False
        )
        assert receiving.status_code == 200, receiving.text
        assert receiving.json()["status"] == "receiving"

        box = await client.post(f"{BASE}/{request_id}/boxes", headers=headers)
        assert box.status_code == 201, box.text
        box_id = box.json()["id"]
        for product_id in order:
            put_line = await client.put(
                f"{BASE}/{request_id}/boxes/{box_id}/lines/{product_id}",
                headers=headers,
                json={"quantity": QUANTITY_PER_PRODUCT},
            )
            assert put_line.status_code == 200, put_line.text
        close_box = await client.post(
            f"{BASE}/{request_id}/boxes/{box_id}/close", headers=headers
        )
        assert close_box.status_code == 200, close_box.text

    return headers, request_ids, product_ids, locations


def _assert_successful_posts(results: Sequence[Response | BaseException]) -> None:
    failures = [
        f"{type(result).__name__}: {result}"
        if isinstance(result, BaseException)
        else f"HTTP {result.status_code}: {result.text}"
        for result in results
        if isinstance(result, BaseException) or result.status_code != 200
    ]
    assert not failures, "Concurrent inbound operation failed: " + "; ".join(failures)


async def _positive_balances(
    product_ids: Sequence[str],
) -> dict[tuple[str, str], int]:
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(
                    InventoryBalance.product_id,
                    InventoryBalance.storage_location_id,
                    func.sum(InventoryBalance.quantity),
                )
                .where(
                    InventoryBalance.product_id.in_(
                        [uuid.UUID(product_id) for product_id in product_ids]
                    ),
                    InventoryBalance.quantity > 0,
                )
                .group_by(
                    InventoryBalance.product_id,
                    InventoryBalance.storage_location_id,
                )
            )
        ).all()
    return {
        (str(product_id), str(location_id)): int(quantity)
        for product_id, location_id, quantity in rows
    }


@pytest.mark.asyncio
async def test_wms744_simultaneous_receiving_completion_locks_shared_products_without_deadlock(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row locks are required")

    headers, request_ids, product_ids, _locations = await _seed_two_receipts(async_client)
    request_order = {
        uuid.UUID(request_ids[0]): [uuid.UUID(pid) for pid in product_ids],
        uuid.UUID(request_ids[1]): [uuid.UUID(pid) for pid in reversed(product_ids)],
    }
    barrier = asyncio.Barrier(2)
    arrived: set[int] = set()
    original_get_request = intake_svc.get_request

    async def get_request_at_same_start(
        session: AsyncSession,
        tenant_id: uuid.UUID,
        request_id: uuid.UUID,
        **kwargs: object,
    ):
        request = await original_get_request(
            session, tenant_id, request_id, **kwargs  # type: ignore[arg-type]
        )
        order = request_order.get(request_id)
        if request is not None and kwargs.get("for_update") and order is not None:
            order_index = {product_id: index for index, product_id in enumerate(order)}
            request.lines.sort(key=lambda line: order_index[line.product_id])
            if id(session) not in arrived:
                arrived.add(id(session))
                await asyncio.wait_for(barrier.wait(), timeout=10)
        return request

    monkeypatch.setattr(intake_svc, "get_request", get_request_at_same_start)
    results = await asyncio.gather(
        *(
            async_client.post(
                f"{BASE}/{request_id}/complete-receiving", headers=headers
            )
            for request_id in request_ids
        ),
        return_exceptions=True,
    )

    assert len(arrived) == 2, "The two HTTP requests must use separate database sessions"
    _assert_successful_posts(results)
    assert [result.json()["status"] for result in results if isinstance(result, Response)] == [
        "sorting",
        "sorting",
    ]

    balances = await _positive_balances(product_ids)
    assert len(balances) == 2
    assert {product_id for product_id, _location_id in balances} == set(product_ids)
    assert set(balances.values()) == {2 * QUANTITY_PER_PRODUCT}


@pytest.mark.asyncio
async def test_wms744_simultaneous_box_putaway_locks_shared_products_without_deadlock(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row locks are required")

    headers, request_ids, product_ids, locations = await _seed_two_receipts(async_client)
    for request_id in request_ids:
        completed = await async_client.post(
            f"{BASE}/{request_id}/complete-receiving", headers=headers
        )
        assert completed.status_code == 200, completed.text
        assert completed.json()["status"] == "sorting"

    request_order = {
        uuid.UUID(request_ids[0]): [uuid.UUID(pid) for pid in product_ids],
        uuid.UUID(request_ids[1]): [uuid.UUID(pid) for pid in reversed(product_ids)],
    }
    barrier = asyncio.Barrier(2)
    arrived: set[int] = set()
    original_get_box = intake_svc._get_box_for_putaway

    async def get_box_at_same_start(
        session: AsyncSession,
        tenant_id: uuid.UUID,
        request_id: uuid.UUID,
        box_id: uuid.UUID,
    ):
        request, box = await original_get_box(session, tenant_id, request_id, box_id)
        order = request_order[request_id]
        order_index = {product_id: index for index, product_id in enumerate(order)}
        box.lines.sort(key=lambda line: order_index[line.product_id])
        if id(session) not in arrived:
            arrived.add(id(session))
            await asyncio.wait_for(barrier.wait(), timeout=10)
        return request, box

    monkeypatch.setattr(intake_svc, "_get_box_for_putaway", get_box_at_same_start)
    box_ids = []
    for request_id in request_ids:
        request = await async_client.get(f"{BASE}/{request_id}", headers=headers)
        assert request.status_code == 200, request.text
        box_ids.append(request.json()["boxes"][0]["id"])

    results = await asyncio.gather(
        *(
            async_client.post(
                f"{BASE}/{request_id}/boxes/{box_id}/putaway",
                headers=headers,
                json={"storage_location_id": location_id},
            )
            for request_id, box_id, location_id in zip(
                request_ids, box_ids, locations, strict=True
            )
        ),
        return_exceptions=True,
    )

    assert len(arrived) == 2, "The two HTTP requests must use separate database sessions"
    _assert_successful_posts(results)
    assert [result.json()["status"] for result in results if isinstance(result, Response)] == [
        "done",
        "done",
    ]

    expected = {
        (product_id, location_id): QUANTITY_PER_PRODUCT
        for product_id in product_ids
        for location_id in locations
    }
    assert await _positive_balances(product_ids) == expected
