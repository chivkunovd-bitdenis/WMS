"""WMS-612: legacy marketplace aliases must not break typed FBS read responses."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import event, select

from app.db.session import SessionLocal, engine
from app.models.fbs_assembly_task import FbsAssemblyTask, FbsAssemblyTaskSupply
from app.models.fbs_order import FbsOrder
from app.models.fbs_supply import FbsSupply
from app.models.product import Product
from app.services.fbs_stock_publish_service import drain_background_stock_publish_tasks
from app.services.fbs_stock_sync_service import drain_zero_publish_background_tasks
from app.services.sorting_location_service import get_or_create_sorting_location
from tests.test_fbs_worklist_query_count import _setup_ff_admin_with_stock


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["packed", "in_delivery", "done"])
async def test_legacy_workspace_and_related_reads_are_canonical_isolated_and_read_only(
    async_client: AsyncClient, status: str,
) -> None:
    headers, seller_id, warehouse_id, product_id, _, order_ids = (
        await _setup_ff_admin_with_stock(async_client, order_count=8)
    )
    foreign_headers, _, _, _, _, _ = await _setup_ff_admin_with_stock(
        async_client, order_count=0,
    )
    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        assert product is not None
        supply = FbsSupply(
            tenant_id=product.tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
            marketplace="wildberries", name="Legacy eight orders", status=status,
            wb_supply_id="WB-GI-LEGACY-WORKSPACE", delivery_type="warehouse_sc",
        )
        session.add(supply)
        await session.flush()
        orders = list((await session.scalars(select(FbsOrder).where(
            FbsOrder.id.in_(order_ids),
        ))).all())
        for order in orders:
            order.supply_id = supply.id
            order.marketplace = "wildberries"
            order.status = status
        task = FbsAssemblyTask(
            tenant_id=product.tenant_id, number="000001", idempotency_key="legacy-task",
            supply_links=[FbsAssemblyTaskSupply(supply_id=supply.id)],
        )
        session.add(task)
        # Normal warehouses already have this system location; keep its lazy
        # creation outside the SQL side-effect measurement for read responses.
        await get_or_create_sorting_location(session, product.tenant_id, warehouse_id)
        await session.commit()
        supply_id, task_id = str(supply.id), str(task.id)
        original_supply = (supply.marketplace, supply.updated_at)
        for order in orders:
            await session.refresh(order)
        original_orders = {order.id: (order.marketplace, order.updated_at) for order in orders}
    await drain_background_stock_publish_tasks()
    await drain_zero_publish_background_tasks()
    statements: list[str] = []

    def capture(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement.lstrip().split(None, 1)[0].upper())

    event.listen(engine.sync_engine, "before_cursor_execute", capture)
    try:
        workspace = await async_client.get(
            f"/operations/fbs-supplies/{supply_id}/workspace", headers=headers,
        )
        assert workspace.status_code == 200, workspace.text
        payload = workspace.json()
        assert payload["supply"]["marketplace"] == "wb"
        assert {row["id"] for row in payload["orders"]} == {str(oid) for oid in order_ids}
        assert all(row["marketplace"] == "wb" for row in payload["orders"])
        assert payload["progress"]["total"] == 8
        supply_response = await async_client.get(
            f"/operations/fbs-supplies/{supply_id}", headers=headers,
        )
        assert supply_response.status_code == 200, supply_response.text
        assert supply_response.json()["marketplace"] == "wb"
        for path in ("/operations/fbs-orders", "/operations/fbs-orders/worklist"):
            response = await async_client.get(path, headers=headers)
            assert response.status_code == 200, response.text
            body = response.json()
            rows = body if isinstance(body, list) else body["items"]
            assert {row["id"] for row in rows} == {str(oid) for oid in order_ids}
            assert all(row["marketplace"] == "wb" for row in rows)
        assembly = await async_client.get(
            f"/operations/fbs-assembly-tasks/{task_id}", headers=headers,
        )
        assert assembly.status_code == 200, assembly.text
        assert assembly.json()["supplies"][0]["marketplace"] == "wb"
        assert assembly.json()["supplies"][0]["orders_count"] == 8
        for path in (
            f"/operations/fbs-supplies/{supply_id}/workspace",
            f"/operations/fbs-supplies/{supply_id}",
            f"/operations/fbs-assembly-tasks/{task_id}",
        ):
            denied = await async_client.get(path, headers=foreign_headers)
            assert denied.status_code == 404, denied.text
        for path in ("/operations/fbs-orders", "/operations/fbs-orders/worklist"):
            response = await async_client.get(path, headers=foreign_headers)
            assert response.status_code == 200, response.text
            body = response.json()
            rows = body if isinstance(body, list) else body["items"]
            assert rows == []
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture)
    assert not {"INSERT", "UPDATE", "DELETE"}.intersection(statements)
    async with SessionLocal() as session:
        stored = await session.get(FbsSupply, uuid.UUID(supply_id))
        assert stored is not None
        assert (stored.marketplace, stored.updated_at) == original_supply
        for order_id, original in original_orders.items():
            stored_order = await session.get(FbsOrder, order_id)
            assert stored_order is not None
            assert (stored_order.marketplace, stored_order.updated_at) == original


@pytest.mark.asyncio
async def test_legacy_preflight_summary_preserves_stored_order(async_client: AsyncClient) -> None:
    headers, _, _, _, _, order_ids = await _setup_ff_admin_with_stock(async_client)
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_ids[0])
        assert order is not None
        order.marketplace = "wildberries"
        await session.commit()
        await session.refresh(order)
        updated_at = order.updated_at
    response = await async_client.post(
        "/operations/fbs-supplies/preflight", headers=headers,
        json={"order_ids": [str(order_ids[0])], "planned_delivery_type": "warehouse_sc"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["summary"]["marketplace"] == "wb"
    async with SessionLocal() as session:
        order = await session.get(FbsOrder, order_ids[0])
        assert order is not None
        assert order.marketplace == "wildberries"
        assert order.updated_at == updated_at
