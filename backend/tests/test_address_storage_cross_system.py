from __future__ import annotations

import time

import pytest
from httpx import AsyncClient
from inbound_box_intake_helpers import (
    fulfill_inbound_via_box_scans,
    post_primary_accept,
    set_planned_boxes,
)


@pytest.mark.asyncio
async def test_tenant_without_address_storage_never_needs_or_sees_a_cell(
    async_client: AsyncClient,
) -> None:
    suffix = str(time.time_ns())
    registration = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "No address storage",
            "slug": f"no-address-{suffix}",
            "admin_email": f"no-address-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registration.status_code == 200, registration.text
    headers = {
        "Authorization": f"Bearer {registration.json()['access_token']}"
    }

    warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "Без адресов", "code": f"no-address-{suffix[-8:]}"},
    )
    assert warehouse.status_code == 200, warehouse.text
    warehouse_id = warehouse.json()["id"]
    old_cell = await async_client.post(
        f"/warehouses/{warehouse_id}/locations",
        headers=headers,
        json={"code": "OLD-CELL"},
    )
    assert old_cell.status_code == 200, old_cell.text

    product = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "Товар без адреса",
            "sku_code": f"NO-ADDR-{suffix}",
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
        },
    )
    assert product.status_code == 200, product.text
    product_id = product.json()["id"]
    sku_code = product.json()["sku_code"]

    disabled = await async_client.patch(
        "/tenant/settings",
        headers=headers,
        json={"address_storage_enabled": False},
    )
    assert disabled.status_code == 200, disabled.text

    locations = await async_client.get(
        f"/warehouses/{warehouse_id}/locations", headers=headers
    )
    assert locations.status_code == 200, locations.text
    assert locations.json() == []
    create_cell = await async_client.post(
        f"/warehouses/{warehouse_id}/locations",
        headers=headers,
        json={"code": "SHOULD-NOT-EXIST"},
    )
    assert create_cell.status_code == 409
    assert create_cell.json()["detail"] == "address_storage_disabled"
    sorting_location = await async_client.get(
        f"/warehouses/{warehouse_id}/sorting-location", headers=headers
    )
    assert sorting_location.status_code == 409
    assert sorting_location.json()["detail"] == "address_storage_disabled"
    cell_balance = await async_client.get(
        "/operations/inventory-balances",
        headers=headers,
        params={"storage_location_id": old_cell.json()["id"]},
    )
    assert cell_balance.status_code == 409
    assert cell_balance.json()["detail"] == "address_storage_disabled"

    inbound_base = "/operations/inbound-intake-requests"
    inbound = await async_client.post(
        inbound_base,
        headers=headers,
        json={"warehouse_id": warehouse_id},
    )
    assert inbound.status_code == 201, inbound.text
    inbound_id = inbound.json()["id"]
    inbound_line = await async_client.post(
        f"{inbound_base}/{inbound_id}/lines",
        headers=headers,
        json={"product_id": product_id, "expected_qty": 8},
    )
    assert inbound_line.status_code == 201, inbound_line.text
    assert inbound_line.json()["storage_location_id"] is None
    assert inbound_line.json()["storage_location_code"] is None
    await set_planned_boxes(async_client, inbound_base, inbound_id, headers)
    submitted = await async_client.post(
        f"{inbound_base}/{inbound_id}/submit", headers=headers
    )
    assert submitted.status_code == 200, submitted.text
    await post_primary_accept(async_client, inbound_base, inbound_id, headers)
    await fulfill_inbound_via_box_scans(
        async_client, headers, inbound_id, sku_code, 8
    )
    verified = await async_client.post(
        f"{inbound_base}/{inbound_id}/verify", headers=headers
    )
    assert verified.status_code == 200, verified.text
    posted = await async_client.post(
        f"{inbound_base}/{inbound_id}/post", headers=headers
    )
    assert posted.status_code == 200, posted.text
    assert posted.json()["status"] == "done"
    assert posted.json()["lines"][0]["posted_qty"] == 8
    assert posted.json()["lines"][0]["storage_location_id"] is None
    assert posted.json()["lines"][0]["storage_location_code"] is None

    inbound_movements = await async_client.get(
        f"{inbound_base}/{inbound_id}/movements", headers=headers
    )
    assert inbound_movements.status_code == 200, inbound_movements.text
    assert inbound_movements.json()
    assert all(
        row["storage_location_id"] is None for row in inbound_movements.json()
    )

    summary = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=headers,
        params={"warehouse_id": warehouse_id},
    )
    assert summary.status_code == 200, summary.text
    stock = next(row for row in summary.json() if row["product_id"] == product_id)
    assert stock["quantity"] == 8
    assert stock["quantity_in_sorting"] == 0
    assert stock["quantity_in_storage"] == 8
    assert stock["available"] == 8

    hints = await async_client.get(
        "/operations/inventory-balances/locations-by-product",
        headers=headers,
        params={"warehouse_id": warehouse_id, "product_id": product_id},
    )
    assert hints.status_code == 200, hints.text
    assert hints.json() == []

    packaging = await async_client.post(
        "/operations/packaging-tasks",
        headers=headers,
        json={
            "warehouse_id": warehouse_id,
            "lines": [{"product_id": product_id, "quantity": 2}],
        },
    )
    assert packaging.status_code == 201, packaging.text
    assert packaging.json()["lines"][0]["storage_location_id"] is None
    assert packaging.json()["lines"][0]["storage_location_code"] is None

    outbound_base = "/operations/outbound-shipment-requests"
    outbound = await async_client.post(
        outbound_base,
        headers=headers,
        json={"warehouse_id": warehouse_id},
    )
    assert outbound.status_code == 201, outbound.text
    outbound_id = outbound.json()["id"]
    outbound_line = await async_client.post(
        f"{outbound_base}/{outbound_id}/lines",
        headers=headers,
        json={"product_id": product_id, "quantity": 3},
    )
    assert outbound_line.status_code == 201, outbound_line.text
    assert outbound_line.json()["storage_location_id"] is None
    assert outbound_line.json()["storage_location_code"] is None
    submitted_outbound = await async_client.post(
        f"{outbound_base}/{outbound_id}/submit", headers=headers
    )
    assert submitted_outbound.status_code == 200, submitted_outbound.text
    posted_outbound = await async_client.post(
        f"{outbound_base}/{outbound_id}/post", headers=headers
    )
    assert posted_outbound.status_code == 200, posted_outbound.text
    assert posted_outbound.json()["status"] == "posted"
    assert posted_outbound.json()["lines"][0]["storage_location_id"] is None
    assert posted_outbound.json()["lines"][0]["storage_location_code"] is None

    outbound_movements = await async_client.get(
        f"{outbound_base}/{outbound_id}/movements", headers=headers
    )
    assert outbound_movements.status_code == 200, outbound_movements.text
    assert outbound_movements.json()[0]["storage_location_id"] is None

    movements = await async_client.get(
        "/operations/inventory-movements", headers=headers
    )
    assert movements.status_code == 200, movements.text
    assert movements.json()
    assert all(row["storage_location_id"] is None for row in movements.json())

    transfer = await async_client.post(
        "/operations/stock-transfers",
        headers=headers,
        json={
            "from_storage_location_id": old_cell.json()["id"],
            "to_storage_location_id": old_cell.json()["id"],
            "product_id": product_id,
            "quantity": 1,
        },
    )
    assert transfer.status_code == 409
    assert transfer.json()["detail"] == "address_storage_disabled"
