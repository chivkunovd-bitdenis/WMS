from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.warehouse import Warehouse
from app.services.tokens import decode_access_token


async def _report_context(
    async_client: AsyncClient,
) -> tuple[dict[str, str], uuid.UUID, str, str, str]:
    suffix = str(int(time.time() * 1000))
    registered = await async_client.post("/auth/register", json={
        "organization_name": "Inventory reports", "slug": f"inventory-{suffix}",
        "admin_email": f"inventory-{suffix}@example.com", "password": "password123",
    })
    token = str(registered.json()["access_token"])
    headers = {"Authorization": f"Bearer {token}"}
    seller = await async_client.post("/sellers", headers=headers, json={"name": "Seller"})
    warehouse = await async_client.post(
        "/warehouses", headers=headers, json={"name": "Main", "code": f"main-{suffix}"}
    )
    location = await async_client.post(
        f"/warehouses/{warehouse.json()['id']}/locations", headers=headers, json={"code": "A-01"}
    )
    return (
        headers,
        uuid.UUID(str(decode_access_token(token)["tenant_id"])),
        seller.json()["id"],
        warehouse.json()["id"],
        location.json()["id"],
    )


async def _seed_product_movement(
    *, tenant_id: uuid.UUID, seller_id: str, warehouse_id: str, location_id: str,
    number: int, quantity_delta: int = 1, movement_type: str = "inbound_intake",
    transfer_group_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
) -> str:
    product_id = product_id or uuid.uuid4()
    async with SessionLocal() as session:
        if await session.get(Product, product_id) is None:
            session.add(Product(
                id=product_id, tenant_id=tenant_id, seller_id=uuid.UUID(seller_id),
                name=f"Product {number:03}", sku_code=f"SKU-{number:03}",
                wb_vendor_code=f"ARTICLE-{number:03}", wb_barcode=f"BARCODE-{number:03}",
            ))
        session.add(InventoryMovement(
            tenant_id=tenant_id, product_id=product_id, seller_id=uuid.UUID(seller_id),
            warehouse_id=uuid.UUID(warehouse_id), storage_location_id=uuid.UUID(location_id),
            quantity_delta=quantity_delta, movement_type=movement_type,
            transfer_group_id=transfer_group_id, created_at=datetime(2026, 8, 1, 12, tzinfo=UTC),
        ))
        await session.commit()
    return str(product_id)


@pytest.mark.asyncio
async def test_reports_inventory_paginates_aggregates_and_searches_all_product_fields(
    async_client: AsyncClient,
) -> None:
    headers, tenant_id, seller_id, warehouse_id, location_id = await _report_context(async_client)
    for number in range(51):
        await _seed_product_movement(
            tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
            location_id=location_id, number=number,
        )
    params = {"date_from": "2026-08-01T00:00:00Z", "date_to": "2026-08-02T00:00:00Z"}
    first_page = await async_client.get("/reports/inventory", headers=headers, params=params)
    assert first_page.status_code == 200
    assert first_page.json()["page_size"] == 50
    assert first_page.json()["total"] == 51
    assert [row["sku_code"] for row in first_page.json()["rows"]] == [
        f"SKU-{number:03}" for number in range(50)
    ]
    second_page = await async_client.get(
        "/reports/inventory", headers=headers, params={**params, "page": 2}
    )
    assert second_page.json()["total"] == 51
    assert [row["sku_code"] for row in second_page.json()["rows"]] == ["SKU-050"]

    for search in ("Product 017", "ARTICLE-017", "SKU-017", "BARCODE-017"):
        response = await async_client.get(
            "/reports/inventory", headers=headers, params={**params, "search": search}
        )
        assert response.status_code == 200
        assert [row["sku_code"] for row in response.json()["rows"]] == ["SKU-017"]


@pytest.mark.asyncio
async def test_reports_inventory_uses_only_whitelisted_sorting_and_groupings(
    async_client: AsyncClient,
) -> None:
    headers, tenant_id, seller_id, warehouse_id, location_id = await _report_context(async_client)
    await _seed_product_movement(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
        location_id=location_id, number=1, quantity_delta=2,
    )
    params = {"date_from": "2026-08-01T00:00:00Z", "date_to": "2026-08-02T00:00:00Z"}
    operation = await async_client.get(
        "/reports/inventory", headers=headers, params={**params, "group_by": "operation"}
    )
    assert operation.status_code == 200
    assert operation.json()["group_by"] == "operation"
    assert operation.json()["rows"][0]["operation"] == "Приёмка"
    rejected = await async_client.get(
        "/reports/inventory", headers=headers, params={**params, "sort_by": "warehouse"}
    )
    assert rejected.status_code == 422


@pytest.mark.asyncio
async def test_reports_inventory_hides_transfers_without_warehouse_and_flags_incomplete_pair(
    async_client: AsyncClient,
) -> None:
    headers, tenant_id, seller_id, warehouse_id, location_id = await _report_context(async_client)
    suffix = str(int(time.time() * 1000))
    second_warehouse = await async_client.post(
        "/warehouses", headers=headers, json={"name": "Second", "code": f"second-{suffix}"}
    )
    second_location = await async_client.post(
        f"/warehouses/{second_warehouse.json()['id']}/locations",
        headers=headers,
        json={"code": "B-01"},
    )
    complete_group = uuid.uuid4()
    complete_product_id = uuid.UUID(await _seed_product_movement(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
        location_id=location_id, number=1, quantity_delta=-5,
        movement_type="stock_transfer_out", transfer_group_id=complete_group,
    ))
    await _seed_product_movement(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=second_warehouse.json()["id"],
        location_id=second_location.json()["id"], number=1, quantity_delta=5,
        movement_type="stock_transfer_in", transfer_group_id=complete_group,
        product_id=complete_product_id,
    )
    incomplete_group = uuid.uuid4()
    await _seed_product_movement(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
        location_id=location_id, number=3, quantity_delta=-2,
        movement_type="stock_transfer_out", transfer_group_id=incomplete_group,
    )
    await _seed_product_movement(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
        location_id=location_id, number=4, quantity_delta=3,
    )
    corrupt_group = uuid.uuid4()
    corrupt_product_id = uuid.UUID(await _seed_product_movement(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
        location_id=location_id, number=5, quantity_delta=-4,
        movement_type="stock_transfer_out", transfer_group_id=corrupt_group,
    ))
    await _seed_product_movement(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=second_warehouse.json()["id"],
        location_id=second_location.json()["id"], number=5, quantity_delta=4,
        movement_type="stock_transfer_out", transfer_group_id=corrupt_group,
        product_id=corrupt_product_id,
    )
    async with SessionLocal() as session:
        session.add(Warehouse(
            tenant_id=tenant_id, name="FBS WB Service", code=f"service-{suffix}",
            is_operational=False,
        ))
        await session.commit()

    params = {
        "date_from": "2026-08-01T00:00:00Z",
        "date_to": "2026-08-02T00:00:00Z",
        "group_by": "operation",
    }
    all_warehouses = await async_client.get("/reports/inventory", headers=headers, params=params)
    assert all_warehouses.status_code == 200
    assert all_warehouses.json()["rows"] == [
        {
            "operation": "Приёмка", "in_qty": 3, "out_qty": 0,
            "net": 3, "integrity_error": False,
        }
    ]

    selected_warehouse = await async_client.get(
        "/reports/inventory", headers=headers, params={**params, "warehouse_id": warehouse_id}
    )
    rows = {row["operation"]: row for row in selected_warehouse.json()["rows"]}
    assert rows["Перемещение: ушло"] == {
        "operation": "Перемещение: ушло", "in_qty": 0, "out_qty": 11,
        "net": -11, "integrity_error": True,
    }
    assert rows["Приёмка"]["integrity_error"] is False
