"""WMS-618: real database races and authoritative confirmation snapshots."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, text
from test_marking_print_fbo_bulk import (
    _create_fbo_task_with_lines,
    _import_codes,
    _make_cz_product,
)
from test_packaging_tasks import _inventory_at_location, _register_admin

from app.db.session import SessionLocal, engine
from app.models.marking_code import MarkingCode, MarkingCodeEvent
from app.models.packaging_task import PackagingTaskLine
from app.models.product import Product
from app.models.seller_wildberries_imported_card import SellerWildberriesImportedCard
from app.services import marking_code_service as marking

POSTGRES = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="real row locks required")


@dataclass
class Shipment:
    headers: dict[str, str]
    seller: str
    warehouse: str
    task: str
    products: list[str]
    locations: list[str]
    lines: list[str]

    @property
    def url(self) -> str:
        return f"/operations/marking-codes/packaging-tasks/{self.task}/print-fbo-bulk"


async def _seed(
    client: AsyncClient, *, count: int = 1, headers: dict[str, str] | None = None
) -> Shipment:
    headers = headers or await _register_admin(client)
    tag = uuid.uuid4().hex[:8]
    seller = await client.post(
        "/sellers",
        headers=headers,
        json={
            "name": tag,
            "email": f"{tag}@example.com",
        },
    )
    seller_id = seller.json()["id"]
    warehouse = await client.post("/warehouses", headers=headers, json={"name": tag, "code": tag})
    warehouse_id = warehouse.json()["id"]
    products, locations = [], []
    for index in range(count):
        product, _ = await _make_cz_product(client, headers, seller_id=seller_id, suffix=str(index))
        products.append(product)
        await _import_codes(
            client,
            headers,
            seller_id=seller_id,
            pool_product_id=product,
            serial_prefix=f"{tag}{index}",
            count=3,
            title=f"pool-{index}",
        )
        locations.append(
            await _inventory_at_location(
                client,
                headers,
                warehouse_id=warehouse_id,
                product_id=product,
                qty=10,
                location_code=f"{tag}-{index}",
            )
        )
    task = await _create_fbo_task_with_lines(
        client,
        headers,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        lines=[
            {"product_id": product, "storage_location_id": location, "quantity": 2}
            for product, location in zip(products, locations, strict=True)
        ],
    )
    async with SessionLocal() as session:
        rows = (
            await session.scalars(
                select(PackagingTaskLine).where(
                    PackagingTaskLine.task_id == uuid.UUID(task),
                )
            )
        ).all()
        by_product = {str(line.product_id): str(line.id) for line in rows}
    return Shipment(
        headers,
        seller_id,
        warehouse_id,
        task,
        products,
        locations,
        [by_product[product] for product in products],
    )


async def _print_events(line_ids: list[str]) -> int:
    async with SessionLocal() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(MarkingCodeEvent)
                .where(
                    MarkingCodeEvent.packaging_task_line_id.in_([uuid.UUID(i) for i in line_ids]),
                    MarkingCodeEvent.event_type == "printed",
                )
            )
            or 0
        )


@pytest.mark.asyncio
@POSTGRES
async def test_two_overlapping_http_confirmations_wait_and_reuse_codes(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shipment = await _seed(async_client)
    entered = asyncio.Event()
    release = asyncio.Event()
    second_entered = asyncio.Event()
    pids: list[int] = []
    original_preview = marking._preview_all_lines_print
    original_print = marking.print_fbo_bulk_for_task

    async def observed_print(session: Any, *args: Any, **kwargs: Any) -> Any:
        pids.append(await session.scalar(text("select pg_backend_pid()")))
        if len(pids) == 2:
            second_entered.set()
        return await original_print(session, *args, **kwargs)

    async def gated_preview(*args: Any, **kwargs: Any) -> Any:
        result = await original_preview(*args, **kwargs)
        if not entered.is_set():
            entered.set()
            await release.wait()
        return result

    monkeypatch.setattr(marking, "print_fbo_bulk_for_task", observed_print)
    monkeypatch.setattr(marking, "_preview_all_lines_print", gated_preview)
    first = asyncio.create_task(async_client.post(shipment.url, headers=shipment.headers, json={}))
    second = None
    try:
        await asyncio.wait_for(entered.wait(), 10)
        second = asyncio.create_task(
            async_client.post(shipment.url, headers=shipment.headers, json={})
        )
        await asyncio.wait_for(second_entered.wait(), 10)
        async with SessionLocal() as observer, asyncio.timeout(10):
            while not await observer.scalar(
                text("select :first = any(pg_blocking_pids(:second))"),
                {"first": pids[0], "second": pids[1]},
            ):
                assert not second.done(), "second request did not wait for the FBO task lock"
                await asyncio.sleep(0.01)
        release.set()
        responses = await asyncio.wait_for(asyncio.gather(first, second), 10)
    finally:
        release.set()
        for request in (first, second):
            if request is not None and not request.done():
                request.cancel()
        await asyncio.gather(
            *(request for request in (first, second) if request), return_exceptions=True
        )
    for response in responses:
        assert response.status_code == 200, response.text
        assert response.json()["shortage"] == 0
    assert responses[0].json() == responses[1].json()
    assert len(responses[0].json()["lines"][0]["printed_codes"]) == 2
    assert await _print_events(shipment.lines) == 2


@pytest.mark.asyncio
@POSTGRES
@pytest.mark.parametrize("allow_partial", [False, True])
async def test_actual_shortage_after_preflight_rolls_back_whole_batch(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    allow_partial: bool,
) -> None:
    shipment = await _seed(async_client, count=2)
    # A neighboring shipment legitimately draws from the second product's pool.
    neighbor = await _create_fbo_task_with_lines(
        async_client,
        shipment.headers,
        seller_id=shipment.seller,
        warehouse_id=shipment.warehouse,
        lines=[
            {
                "product_id": shipment.products[1],
                "storage_location_id": shipment.locations[1],
                "quantity": 2,
            }
        ],
    )
    async with SessionLocal() as session:
        neighbor_line = await session.scalar(
            select(PackagingTaskLine.id).where(
                PackagingTaskLine.task_id == uuid.UUID(neighbor),
            )
        )
    entered, release = asyncio.Event(), asyncio.Event()
    original = marking._preview_all_lines_print

    async def gated_preview(*args: Any, **kwargs: Any) -> Any:
        result = await original(*args, **kwargs)
        assert sum(line.shortage for line in result) == 0
        entered.set()
        await release.wait()
        return result

    monkeypatch.setattr(marking, "_preview_all_lines_print", gated_preview)
    pending = asyncio.create_task(
        async_client.post(
            shipment.url, headers=shipment.headers, json={"allow_partial": allow_partial}
        )
    )
    try:
        await asyncio.wait_for(entered.wait(), 10)
        consumed = await async_client.post(
            f"/operations/marking-codes/packaging-lines/{neighbor_line}/print",
            headers=shipment.headers,
            json={},
        )
        assert consumed.status_code == 200, consumed.text
        assert consumed.json()["quantity"] == 2
        release.set()
        response = await asyncio.wait_for(pending, 10)
    finally:
        release.set()
        if not pending.done():
            pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["shortage"] == 1
    by_product = {line["product_id"]: line for line in payload["lines"]}
    assert len(by_product[shipment.products[0]]["printed_codes"]) == (2 if allow_partial else 0)
    assert len(by_product[shipment.products[1]]["printed_codes"]) == (1 if allow_partial else 0)
    assert await _print_events(shipment.lines) == (3 if allow_partial else 0)
    async with SessionLocal() as session:
        for product_id, expected in zip(
            shipment.products, (1, 0) if allow_partial else (3, 1), strict=True
        ):
            product = await session.get(Product, uuid.UUID(product_id))
            assert product is not None
            assert (
                await marking.count_available_for_product(
                    session,
                    product.tenant_id,
                    product.id,
                )
                == expected
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("issue", [False, True])
async def test_confirm_reads_changed_composition_and_complete_label_data(
    async_client: AsyncClient,
    issue: bool,
) -> None:
    shipment = await _seed(async_client, count=2)
    opened = await async_client.get(
        f"/operations/packaging-tasks/{shipment.task}", headers=shipment.headers
    )
    assert opened.status_code == 200, opened.text
    assert len(opened.json()["lines"]) == 2
    new_product, new_sku = await _make_cz_product(
        async_client, shipment.headers, seller_id=shipment.seller, suffix="new"
    )
    new_location = await _inventory_at_location(
        async_client,
        shipment.headers,
        warehouse_id=shipment.warehouse,
        product_id=new_product,
        qty=3,
        location_code="new-location",
    )
    # Another operator changes the persisted task after the dialog was opened.
    async with SessionLocal() as session:
        removed = await session.get(PackagingTaskLine, uuid.UUID(shipment.lines[1]))
        assert removed is not None
        await session.delete(removed)
        changed = await session.get(PackagingTaskLine, uuid.UUID(shipment.lines[0]))
        assert changed is not None
        changed.qty_total = 3
        session.add(
            PackagingTaskLine(
                task_id=uuid.UUID(shipment.task),
                product_id=uuid.UUID(new_product),
                storage_location_id=uuid.UUID(new_location),
                qty_total=1,
            )
        )
        product = await session.get(Product, uuid.UUID(new_product))
        assert product is not None
        product.name = "Current name after opening"
        product.wb_barcode = "4600000000613"
        product.wb_vendor_code = "Current article"
        product.wb_size = "XL"
        product.wb_nm_id = 613
        product.requires_honest_sign = False
        session.add(
            SellerWildberriesImportedCard(
                tenant_id=product.tenant_id,
                seller_id=uuid.UUID(shipment.seller),
                nm_id=613,
                raw_json={
                    "brand": "Current brand",
                    "characteristics": [
                        {"name": "Цвет", "value": ["синий"]},
                        {"name": "Состав", "value": ["хлопок"]},
                    ],
                },
            )
        )
        await session.commit()
    confirmed = await async_client.post(
        shipment.url, headers=shipment.headers, json={"issue_marking_codes": issue}
    )
    assert confirmed.status_code == 200, confirmed.text
    payload = confirmed.json()
    assert payload["shortage"] == 0
    lines = {line["product_id"]: line for line in payload["lines"]}
    assert set(lines) == {shipment.products[0], new_product}
    assert lines[shipment.products[0]]["quantity"] == 3
    assert len(lines[shipment.products[0]]["printed_codes"]) == (3 if issue else 0)
    assert lines[new_product]["quantity"] == 1
    assert lines[new_product]["product_label"] == {
        "product_name": "Current name after opening",
        "sku_code": new_sku,
        "barcode": "4600000000613",
        "wb_vendor_code": "Current article",
        "wb_size": "XL",
        "wb_color": "синий",
        "wb_brand": "Current brand",
        "wb_composition": "хлопок",
        "seller_name": opened.json()["lines"][0]["seller_name"],
    }
    if not issue:
        assert await _print_events(shipment.lines) == 0
        async with SessionLocal() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(MarkingCode)
                    .where(
                        MarkingCode.seller_id == uuid.UUID(shipment.seller),
                        MarkingCode.status != "available",
                    )
                )
                == 0
            )


@pytest.mark.asyncio
async def test_snapshot_and_issuance_isolate_neighbor_seller_and_tenant(
    async_client: AsyncClient,
) -> None:
    shipment = await _seed(async_client)
    other_seller = await _seed(async_client, headers=shipment.headers)
    other_tenant = await _seed(async_client)
    neighbor = await _create_fbo_task_with_lines(
        async_client,
        shipment.headers,
        seller_id=shipment.seller,
        warehouse_id=shipment.warehouse,
        lines=[
            {
                "product_id": shipment.products[0],
                "storage_location_id": shipment.locations[0],
                "quantity": 1,
            }
        ],
    )
    response = await async_client.post(shipment.url, headers=shipment.headers, json={})
    assert response.status_code == 200, response.text
    assert {line["product_id"] for line in response.json()["lines"]} == set(shipment.products)
    denied = await async_client.post(shipment.url, headers=other_tenant.headers, json={})
    assert denied.status_code == 404, denied.text
    async with SessionLocal() as session:
        untouched = (
            await session.scalars(
                select(PackagingTaskLine).where(
                    PackagingTaskLine.task_id.in_(
                        [uuid.UUID(t) for t in [neighbor, other_seller.task, other_tenant.task]]
                    ),
                )
            )
        ).all()
        assert len(untouched) == 3
        assert all(line.qty_marking_printed == 0 for line in untouched)
        assert (
            await session.scalar(
                select(func.count())
                .select_from(MarkingCode)
                .where(
                    MarkingCode.packaging_task_line_id.in_([line.id for line in untouched]),
                )
            )
            == 0
        )
    assert await _print_events(other_seller.lines + other_tenant.lines) == 0
