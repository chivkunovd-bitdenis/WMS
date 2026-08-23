from __future__ import annotations

import csv
import io
import time
import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.db.session import SessionLocal
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.services.tokens import decode_access_token


async def _auth_headers(async_client: AsyncClient) -> dict[str, str]:
    suffix = str(int(time.time() * 1000))
    registered = await async_client.post("/auth/register", json={
        "organization_name": "CSV reports", "slug": f"csv-{suffix}",
        "admin_email": f"csv-{suffix}@example.com", "password": "password123",
    })
    return {"Authorization": f"Bearer {registered.json()['access_token']}"}


async def _report_context(
    async_client: AsyncClient,
) -> tuple[dict[str, str], uuid.UUID, str, str, str]:
    headers = await _auth_headers(async_client)
    token = headers["Authorization"].removeprefix("Bearer ")
    tenant_id = uuid.UUID(str(decode_access_token(token)["tenant_id"]))
    suffix = str(time.time_ns())
    seller = await async_client.post("/sellers", headers=headers, json={"name": "CSV seller"})
    warehouse = await async_client.post(
        "/warehouses", headers=headers, json={"name": "CSV warehouse", "code": f"csv-{suffix}"}
    )
    location = await async_client.post(
        f"/warehouses/{warehouse.json()['id']}/locations", headers=headers, json={"code": "CSV-01"}
    )
    return headers, tenant_id, seller.json()["id"], warehouse.json()["id"], location.json()["id"]


async def _seed_movement(
    *, tenant_id: uuid.UUID, seller_id: str, warehouse_id: str, location_id: str,
    sku: str, name: str, quantity_delta: int,
    movement_type: str = "inbound_intake",
    created_at: datetime | None = None,
    transfer_group_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
) -> uuid.UUID:
    async with SessionLocal() as session:
        product_id = product_id or uuid.uuid4()
        if await session.get(Product, product_id) is None:
            session.add(Product(
                id=product_id, tenant_id=tenant_id, seller_id=uuid.UUID(seller_id),
                name=name, sku_code=sku, wb_vendor_code=f"ARTICLE-{sku}",
                wb_barcode=f"BARCODE-{sku}",
            ))
        session.add(InventoryMovement(
            tenant_id=tenant_id, product_id=product_id, seller_id=uuid.UUID(seller_id),
            warehouse_id=uuid.UUID(warehouse_id), storage_location_id=uuid.UUID(location_id),
            quantity_delta=quantity_delta, movement_type=movement_type,
            transfer_group_id=transfer_group_id,
            created_at=created_at or datetime(2026, 8, 1, 12, tzinfo=UTC),
        ))
        await session.commit()
        return product_id


@pytest.mark.asyncio
async def test_inventory_csv_rejects_empty_slice(async_client: AsyncClient) -> None:
    headers = await _auth_headers(async_client)
    response = await async_client.get("/reports/inventory/export.csv", headers=headers,
        params={"date_from": "2026-08-01T00:00:00Z", "date_to": "2026-08-02T00:00:00Z"})
    assert response.status_code == 422
    assert response.json()["detail"] == "nothing to export for the selected period"


@pytest.mark.asyncio
async def test_inventory_csv_rejects_period_longer_than_366_days(
    async_client: AsyncClient,
) -> None:
    headers = await _auth_headers(async_client)
    response = await async_client.get("/reports/inventory/export.csv", headers=headers,
        params={"date_from": "2025-01-01T00:00:00Z", "date_to": "2026-08-02T00:00:00Z"})
    assert response.status_code == 422
    assert response.json()["detail"] == "period cannot be longer than 366 days"


@pytest.mark.asyncio
async def test_inventory_csv_matches_visible_product_table_columns_and_rows(
    async_client: AsyncClient,
) -> None:
    headers, tenant_id, seller_id, warehouse_id, location_id = await _report_context(async_client)
    await _seed_movement(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
        location_id=location_id, sku="SKU-CSV", name="CSV product", quantity_delta=7,
    )
    params = {"date_from": "2026-08-01T00:00:00Z", "date_to": "2026-08-02T00:00:00Z"}
    table = await async_client.get("/reports/inventory", headers=headers, params=params)
    export = await async_client.get("/reports/inventory/export.csv", headers=headers, params=params)

    assert table.status_code == 200
    assert export.status_code == 200
    csv_rows = list(csv.reader(io.StringIO(export.content.decode("utf-8-sig"))))
    assert csv_rows[0] == [
        "Товар", "Название", "Артикул продавца", "ШК", "Селлер",
        "Остаток сейчас", "Приход", "Расход", "Нетто",
    ]
    row = table.json()["rows"][0]
    assert csv_rows[1] == [
        row["sku_code"], row["product_name"], row["wb_vendor_code"], row["wb_barcode"],
        row["seller_name"], str(row["current_balance"]), str(row["total_in"]),
        str(row["total_out"]), str(row["net"]),
    ]


@pytest.mark.asyncio
async def test_inventory_csv_matches_table_grouping_and_requested_order(
    async_client: AsyncClient,
) -> None:
    headers, tenant_id, seller_id, warehouse_id, location_id = await _report_context(async_client)
    await _seed_movement(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
        location_id=location_id, sku="SKU-IN", name="Incoming", quantity_delta=2,
        movement_type="inbound_intake",
    )
    await _seed_movement(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
        location_id=location_id, sku="SKU-OUT", name="Outgoing", quantity_delta=-7,
        movement_type="outbound_shipment",
    )
    params = {
        "date_from": "2026-08-01T00:00:00Z",
        "date_to": "2026-08-02T00:00:00Z",
        "group_by": "operation",
        "sort_by": "net",
        "sort_order": "desc",
    }

    table = await async_client.get("/reports/inventory", headers=headers, params=params)
    export = await async_client.get("/reports/inventory/export.csv", headers=headers, params=params)

    assert table.status_code == 200
    assert export.status_code == 200
    csv_rows = list(csv.reader(io.StringIO(export.content.decode("utf-8-sig"))))
    assert csv_rows[0] == ["Операция", "Приход", "Расход", "Нетто"]
    assert csv_rows[1:] == [
        [row["operation"], str(row["in_qty"]), str(row["out_qty"]), str(row["net"])]
        for row in table.json()["rows"]
    ]
    assert [row[0] for row in csv_rows[1:]] == ["Приёмка", "Отгрузка"]


# S-33-TC-013: an incomplete transfer must not look like a valid zero in CSV.
@pytest.mark.asyncio
async def test_inventory_csv_marks_incomplete_transfer_like_visible_table(
    async_client: AsyncClient,
) -> None:
    headers, tenant_id, seller_id, warehouse_id, location_id = await _report_context(async_client)
    await _seed_movement(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        location_id=location_id,
        sku="SKU-INCOMPLETE-TRANSFER",
        name="Incomplete transfer",
        quantity_delta=-3,
        movement_type="stock_transfer_out",
        transfer_group_id=uuid.uuid4(),
    )
    params = {
        "date_from": "2026-08-01T00:00:00Z",
        "date_to": "2026-08-02T00:00:00Z",
        "group_by": "operation",
        "warehouse_id": warehouse_id,
    }

    table = await async_client.get("/reports/inventory", headers=headers, params=params)
    export = await async_client.get("/reports/inventory/export.csv", headers=headers, params=params)

    assert table.status_code == 200
    assert export.status_code == 200
    table_row = table.json()["rows"][0]
    assert table_row == {
        "operation": "Перемещение: ушло",
        "in_qty": 0,
        "out_qty": 3,
        "net": -3,
        "integrity_error": True,
    }
    csv_rows = list(csv.reader(io.StringIO(export.content.decode("utf-8-sig"))))
    assert csv_rows == [
        ["Операция", "Приход", "Расход", "Нетто"],
        [
            f"{table_row['operation']} (Ошибка)",
            "—",
            str(table_row["out_qty"]),
            str(table_row["net"]),
        ],
    ]
    assert ["Перемещение: ушло", "0", "3", "-3"] not in csv_rows


# S-33-TC-004: a complete pair keeps the ordinary table-shaped CSV values.
@pytest.mark.asyncio
async def test_inventory_csv_keeps_complete_transfer_values_unchanged(
    async_client: AsyncClient,
) -> None:
    headers, tenant_id, seller_id, warehouse_id, location_id = await _report_context(async_client)
    suffix = str(time.time_ns())
    second_warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "CSV destination", "code": f"csv-destination-{suffix}"},
    )
    second_location = await async_client.post(
        f"/warehouses/{second_warehouse.json()['id']}/locations",
        headers=headers,
        json={"code": "CSV-02"},
    )
    transfer_group_id = uuid.uuid4()
    product_id = await _seed_movement(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        location_id=location_id,
        sku="SKU-COMPLETE-TRANSFER",
        name="Complete transfer",
        quantity_delta=-4,
        movement_type="stock_transfer_out",
        transfer_group_id=transfer_group_id,
    )
    await _seed_movement(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=second_warehouse.json()["id"],
        location_id=second_location.json()["id"],
        sku="SKU-COMPLETE-TRANSFER",
        name="Complete transfer",
        quantity_delta=4,
        movement_type="stock_transfer_in",
        transfer_group_id=transfer_group_id,
        product_id=product_id,
    )
    params = {
        "date_from": "2026-08-01T00:00:00Z",
        "date_to": "2026-08-02T00:00:00Z",
        "group_by": "operation",
        "warehouse_id": warehouse_id,
    }

    table = await async_client.get("/reports/inventory", headers=headers, params=params)
    export = await async_client.get("/reports/inventory/export.csv", headers=headers, params=params)

    assert table.status_code == 200
    assert export.status_code == 200
    table_row = table.json()["rows"][0]
    assert table_row["integrity_error"] is False
    csv_rows = list(csv.reader(io.StringIO(export.content.decode("utf-8-sig"))))
    assert csv_rows[1] == [
        table_row["operation"],
        str(table_row["in_qty"]),
        str(table_row["out_qty"]),
        str(table_row["net"]),
    ]


@pytest.mark.asyncio
async def test_inventory_csv_uses_same_moscow_calendar_boundaries_as_table(
    async_client: AsyncClient,
) -> None:
    headers, tenant_id, seller_id, warehouse_id, location_id = await _report_context(async_client)
    await _seed_movement(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
        location_id=location_id, sku="SKU-INCLUDED", name="Included", quantity_delta=1,
        created_at=datetime(2026, 7, 31, 22, 30, tzinfo=UTC),
    )
    await _seed_movement(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
        location_id=location_id, sku="SKU-EXCLUDED", name="Excluded", quantity_delta=1,
        created_at=datetime(2026, 8, 1, 21, 0, tzinfo=UTC),
    )
    params = {"date_from": "2026-08-01T00:00:00", "date_to": "2026-08-02T00:00:00"}

    table = await async_client.get("/reports/inventory", headers=headers, params=params)
    export = await async_client.get("/reports/inventory/export.csv", headers=headers, params=params)

    assert table.status_code == 200
    assert export.status_code == 200
    csv_rows = list(csv.reader(io.StringIO(export.content.decode("utf-8-sig"))))
    assert [row[0] for row in csv_rows[1:]] == [
        row["sku_code"] for row in table.json()["rows"]
    ] == ["SKU-INCLUDED"]


@pytest.mark.asyncio
async def test_inventory_csv_for_seller_ignores_requested_foreign_seller_scope(
    async_client: AsyncClient,
) -> None:
    admin_headers, tenant_id, seller_id, warehouse_id, location_id = await _report_context(
        async_client
    )
    other_seller = await async_client.post(
        "/sellers", headers=admin_headers, json={"name": "Other seller"}
    )
    await _seed_movement(
        tenant_id=tenant_id, seller_id=seller_id, warehouse_id=warehouse_id,
        location_id=location_id, sku="SKU-OWN", name="Own product", quantity_delta=3,
    )
    await _seed_movement(
        tenant_id=tenant_id, seller_id=other_seller.json()["id"], warehouse_id=warehouse_id,
        location_id=location_id, sku="SKU-FOREIGN", name="Foreign product", quantity_delta=5,
    )
    email = f"csv-scope-{time.time_ns()}@example.com"
    account = await async_client.post(
        "/auth/seller-accounts", headers=admin_headers,
        json={"seller_id": seller_id, "email": email, "password": "password123"},
    )
    assert account.status_code == 201, account.text
    login = await async_client.post("/auth/login", json={"email": email, "password": "password123"})
    seller_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    export = await async_client.get(
        "/reports/inventory/export.csv", headers=seller_headers,
        params={
            "date_from": "2026-08-01T00:00:00Z", "date_to": "2026-08-02T00:00:00Z",
            "seller_id": other_seller.json()["id"],
        },
    )

    assert export.status_code == 200
    csv_rows = list(csv.reader(io.StringIO(export.content.decode("utf-8-sig"))))
    assert csv_rows[0] == [
        "Товар", "Название", "Артикул продавца", "ШК", "Остаток сейчас",
        "Приход", "Расход", "Нетто",
    ]
    assert len(csv_rows) == 2
    assert csv_rows[1][0:2] == ["SKU-OWN", "Own product"]
    assert "Foreign product" not in export.text
