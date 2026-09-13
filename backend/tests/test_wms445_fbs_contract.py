"""WMS-445: TSD reads the same order, route and packing facts as the web."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder, FbsOrderProduct
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.packaging_task import PackagingTask
from app.models.product import Product
from app.models.storage_location import StorageLocation
from app.services import inventory_service
from tests.inventory_actor_helpers import resolve_test_actor_user_id
from tests.test_fbs_picking import (
    _create_product,
    _create_seller_and_warehouse,
    _register_ff_admin,
    _scan_product,
    _seed_pick_supply,
    _workspace,
)


async def _case(client: AsyncClient, marketplace: str) -> dict[str, Any]:
    headers, suffix, tenant = await _register_ff_admin(client)
    seller, warehouse, source = await _create_seller_and_warehouse(client, headers, suffix)
    barcode = f"445-{suffix}"
    product = await _create_product(client, headers, seller, sku=barcode, barcode=barcode)
    supply, orders, _ = await _seed_pick_supply(
        client,
        headers,
        tenant,
        seller,
        warehouse,
        source,
        product,
        stock_qty=8,
        order_specs=[(1, timedelta(hours=48)), (2, timedelta(hours=12))],
        barcode=barcode,
        marketplace=marketplace,
        position_quantity=2,
    )
    async with SessionLocal() as session:
        older = await session.get(FbsOrder, orders[0])
        newer = await session.get(FbsOrder, orders[1])
        assert older and newer
        older.created_at_wb = datetime.now(UTC) - timedelta(days=2)
        newer.created_at_wb = datetime.now(UTC) - timedelta(hours=1)
        source2 = StorageLocation(
            tenant_id=tenant, warehouse_id=warehouse, code="WMS445-SECOND", barcode="WMS445-SOURCE2"
        )
        session.add(source2)
        await session.flush()
        await inventory_service.record_movement_and_adjust_balance(
            session,
            tenant_id=tenant,
            product_id=product,
            storage_location_id=source2.id,
            quantity_delta=8,
            movement_type="inbound_intake",
            actor_user_id=await resolve_test_actor_user_id(session, tenant),
        )
        await session.commit()
        second_source = source2.id
    return dict(
        headers=headers,
        tenant=tenant,
        seller=seller,
        warehouse=warehouse,
        source=source,
        source2=second_source,
        product=product,
        barcode=barcode,
        supply=supply,
        orders=orders,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("marketplace", ["wb", "ozon"])
async def test_scan_oldest_order_not_nearest_deadline_and_retry(
    async_client: AsyncClient,
    marketplace: str,
) -> None:
    case = await _case(async_client, marketplace)
    kwargs = dict(
        location_id=case["source"], barcode=case["barcode"], idempotency_key="445-physical-scan-1"
    )
    first = await _scan_product(async_client, case["headers"], case["supply"], **kwargs)
    assert first.status_code == 200, first.text
    rows = {row["id"]: row for row in first.json()["orders"]}
    old, new = (rows[str(order)] for order in case["orders"])
    if marketplace == "ozon":
        assert old["positions"][0]["picked_quantity"] == 1
        assert new["positions"][0]["picked_quantity"] == 0
    else:
        assert old["pick"]["status"] == "picked"
        assert new["pick"]["status"] == "pending"
    retry = await _scan_product(async_client, case["headers"], case["supply"], **kwargs)
    assert retry.status_code == 200, retry.text
    assert retry.json()["progress"] == first.json()["progress"]
    second = await _scan_product(
        async_client,
        case["headers"],
        case["supply"],
        location_id=case["source2"],
        barcode=case["barcode"],
        idempotency_key="445-physical-scan-2",
    )
    assert second.status_code == 200, second.text
    reread = await _workspace(async_client, case["headers"], case["supply"])
    assert reread.json()["progress"]["picked"] == 2
    if marketplace == "ozon":
        rows = {row["id"]: row for row in reread.json()["orders"]}
        assert rows[str(case["orders"][0])]["positions"][0]["picked_quantity"] == 2
        assert rows[str(case["orders"][1])]["positions"][0]["picked_quantity"] == 0


@pytest.mark.asyncio
async def test_ozon_route_and_big_warehouse_survive_public_responses(
    async_client: AsyncClient,
) -> None:
    case = await _case(async_client, "ozon")
    async with SessionLocal() as session:
        for order_id in case["orders"]:
            order = await session.get(FbsOrder, order_id)
            assert order
            order.wb_warehouse_id = 1020005029603630
            order.meta_details_json = {
                "ozon_delivery_method_name": "ПВЗ Ozon Садовая",
                "ozon_delivery_method_id": "445",
            }
        await session.commit()
    responses = [
        await async_client.post(
            "/operations/fbs-supplies/preflight",
            headers=case["headers"],
            json={
                "order_ids": [str(order) for order in case["orders"]],
                "planned_delivery_type": "warehouse_sc",
            },
        ),
        await async_client.get(
            "/operations/fbs-supplies/worklist?marketplace=ozon", headers=case["headers"]
        ),
        await _workspace(async_client, case["headers"], case["supply"]),
    ]
    for response in responses:
        assert response.status_code == 200, response.text
    summary = responses[0].json()["summary"]
    listed = responses[1].json()["items"][0]
    opened = responses[2].json()["supply"]
    for data in (summary, listed, opened):
        assert data["marketplace"] == "ozon"
        assert data["delivery_route"] == "ПВЗ Ozon Садовая"
        assert int(data["wb_warehouse"]["id"]) == 1020005029603630
    assert listed["delivery_type"] == "warehouse_sc"


@pytest.mark.asyncio
async def test_ozon_position_packing_counts_reread_retry_without_stock_change(
    async_client: AsyncClient,
) -> None:
    case = await _case(async_client, "ozon")
    async with SessionLocal() as session:
        other = Product(
            tenant_id=case["tenant"],
            seller_id=case["seller"],
            name="Вторая позиция",
            sku_code="WMS445-SECOND",
        )
        session.add(other)
        await session.flush()
        session.add(
            FbsOrderProduct(
                order_id=case["orders"][0],
                product_id=other.id,
                position_index=1,
                quantity=1,
                ozon_sku=445002,
            )
        )
        await session.commit()
        other_id = other.id
    started = await async_client.post(
        f"/operations/fbs-supplies/{case['supply']}/start-work",
        headers=case["headers"],
    )
    assert started.status_code == 200, started.text
    task_id = started.json()["supply"]["packaging_task_id"]
    task = await async_client.get(f"/operations/packaging-tasks/{task_id}", headers=case["headers"])
    assert task.status_code == 200, task.text
    lines = {line["product_id"]: line["id"] for line in task.json()["lines"]}

    async def stock_snapshot() -> tuple[list[Any], list[Any]]:
        async with SessionLocal() as session:
            return (
                list(
                    (
                        await session.execute(
                            select(InventoryBalance.__table__).order_by(InventoryBalance.id)
                        )
                    ).all()
                ),
                list(
                    (
                        await session.execute(
                            select(InventoryMovement.__table__).order_by(InventoryMovement.id)
                        )
                    ).all()
                ),
            )

    before = await stock_snapshot()
    for index, product_id in enumerate([case["product"], case["product"], other_id]):
        body = {
            "quantity": 1,
            "order_id": str(case["orders"][0]),
            "idempotency_key": f"445-pack-{index}",
        }
        for _ in range(2):  # Repeat the same physical action after its response is lost.
            response = await async_client.post(
                f"/operations/packaging-tasks/{task_id}/lines/{lines[str(product_id)]}/pack",
                headers=case["headers"],
                json=body,
            )
            assert response.status_code == 200, response.text
        reread = await _workspace(async_client, case["headers"], case["supply"])
        order = next(row for row in reread.json()["orders"] if row["id"] == str(case["orders"][0]))
        assert [p["packed_quantity"] for p in order["positions"]] == [
            min(index + 1, 2),
            int(index == 2),
        ]
        assert await stock_snapshot() == before

    # Later document completion must not turn a successful saved attempt into
    # a failure or a new unit. The transition is deliberately isolated here.
    async with SessionLocal() as session:
        saved_task = await session.get(PackagingTask, uuid.UUID(task_id))
        assert saved_task
        saved_task.status = "done"
        await session.commit()
    url = f"/operations/packaging-tasks/{task_id}/lines/{lines[str(other_id)]}/pack"
    replay_body = {
        "quantity": 1,
        "order_id": str(case["orders"][0]),
        "idempotency_key": "445-pack-2",
    }
    replay = await async_client.post(url, headers=case["headers"], json=replay_body)
    assert replay.status_code == 200, replay.text
    assert replay.json()["packaging_task"]["status"] == "done"
    assert await stock_snapshot() == before
    for change in ({"quantity": 2}, {"order_id": str(case["orders"][1])}):
        conflict = await async_client.post(
            url, headers=case["headers"], json={**replay_body, **change}
        )
        assert conflict.status_code == 409, conflict.text
        assert conflict.json()["detail"] == "idempotency_conflict"
