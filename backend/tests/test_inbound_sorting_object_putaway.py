from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.inventory_balance import InventoryBalance
from app.models.storage_location import StorageLocation


@pytest.mark.asyncio
async def test_sorting_object_place_moves_inbound_box_stock_to_cell(
    async_client: AsyncClient,
) -> None:
    """TC-NEW-INBOUND-BOX-PLACE-001: placing a received box moves its real stock."""
    suffix = f"inbound-box-place-{time.time_ns()}"
    registered = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Inbound box place",
            "slug": suffix,
            "admin_email": f"{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registered.status_code == 200, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    me = await async_client.get("/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    tenant_id = uuid.UUID(me.json()["tenant_id"])

    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "Склад приёмки", "code": f"wh-{time.time_ns()}"},
    )
    assert warehouse.status_code == 200, warehouse.text
    warehouse_id = warehouse.json()["id"]
    cell = await async_client.post(
        f"/warehouses/{warehouse_id}/locations",
        headers=headers,
        json={"code": "A-01-01"},
    )
    assert cell.status_code == 200, cell.text
    cell_id = cell.json()["id"]

    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Товар в коробе приёмки",
            "sku_code": f"SKU-{time.time_ns()}",
            "length_mm": 100,
            "width_mm": 100,
            "height_mm": 100,
        },
    )
    assert product.status_code == 200, product.text
    product_id = product.json()["id"]

    base = "/operations/inbound-intake-requests"
    request = await async_client.post(
        base,
        headers=headers,
        json={"warehouse_id": warehouse_id},
    )
    assert request.status_code == 201, request.text
    request_id = request.json()["id"]
    line = await async_client.post(
        f"{base}/{request_id}/lines",
        headers=headers,
        json={"product_id": product_id, "expected_qty": 4},
    )
    assert line.status_code == 201, line.text
    receiving = await async_client.post(
        f"{base}/{request_id}/begin-receiving",
        headers=headers,
    )
    assert receiving.status_code == 200, receiving.text
    assert receiving.json()["status"] == "receiving"

    box = await async_client.post(f"{base}/{request_id}/boxes", headers=headers)
    assert box.status_code == 201, box.text
    box_id = box.json()["id"]
    filled = await async_client.put(
        f"{base}/{request_id}/boxes/{box_id}/lines/{product_id}",
        headers=headers,
        json={"quantity": 4},
    )
    assert filled.status_code == 200, filled.text
    closed = await async_client.post(
        f"{base}/{request_id}/boxes/{box_id}/close",
        headers=headers,
    )
    assert closed.status_code == 200, closed.text
    verified = await async_client.post(
        f"{base}/{request_id}/verify",
        headers=headers,
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["status"] == "sorting"

    placed = await async_client.post(
        f"/warehouses/{warehouse_id}/sorting-objects/place",
        headers=headers,
        json={
            "kind": "box",
            "id": box_id,
            "cell_id": cell_id,
            "to_id": None,
            "qty": 4,
        },
    )
    assert placed.status_code == 200, placed.text
    assert placed.json()["moved_qty"] == 4

    async with SessionLocal() as session:
        quantities = dict(
            (
                await session.execute(
                    select(StorageLocation.id, func.sum(InventoryBalance.quantity))
                    .join(
                        InventoryBalance,
                        InventoryBalance.storage_location_id == StorageLocation.id,
                    )
                    .where(
                        InventoryBalance.tenant_id == tenant_id,
                        InventoryBalance.product_id == uuid.UUID(product_id),
                    )
                    .group_by(StorageLocation.id)
                )
            ).all()
        )
    assert quantities.get(uuid.UUID(cell_id), 0) == 4
    assert sum(quantities.values()) == 4

    completed = await async_client.get(f"{base}/{request_id}", headers=headers)
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "done"
    assert completed.json()["sorting_remaining_qty"] == 0
    assert completed.json()["boxes"][0]["remaining_qty"] == 0

    repeated = await async_client.post(
        f"/warehouses/{warehouse_id}/sorting-objects/place",
        headers=headers,
        json={
            "kind": "box",
            "id": box_id,
            "cell_id": cell_id,
            "to_id": None,
            "qty": 4,
        },
    )
    assert repeated.status_code == 409, repeated.text
    assert repeated.json()["detail"] == "nothing_to_move"
