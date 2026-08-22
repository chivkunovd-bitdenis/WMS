from __future__ import annotations

import time

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_operational_warehouse_list_and_scan_resolver(async_client: AsyncClient) -> None:
    suffix = str(time.time_ns())
    registered = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Warehouse Scan Co",
            "slug": f"warehouse-scan-{suffix}",
            "admin_email": f"warehouse-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registered.status_code == 200, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

    warehouse = await async_client.post(
        "/warehouses", headers=headers, json={"name": "Основной", "code": "main"}
    )
    assert warehouse.status_code == 200, warehouse.text
    body = warehouse.json()
    assert body["is_operational"] is True
    assert body["barcode"].startswith("WH-")

    listed = await async_client.get("/warehouses", headers=headers)
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [body["id"]]

    warehouse_scan = await async_client.get(
        "/warehouses/resolve", headers=headers, params={"barcode": body["barcode"]}
    )
    assert warehouse_scan.status_code == 200, warehouse_scan.text
    assert warehouse_scan.json()["type"] == "warehouse"

    location = await async_client.post(
        f"/warehouses/{body['id']}/locations", headers=headers, json={"code": "A-01"}
    )
    assert location.status_code == 200, location.text
    location_scan = await async_client.get(
        "/warehouses/resolve",
        headers=headers,
        params={"barcode": location.json()["barcode"]},
    )
    assert location_scan.status_code == 200, location_scan.text
    assert location_scan.json()["type"] == "location"

    second = await async_client.post(
        "/warehouses", headers=headers, json={"name": "Юг", "code": "A-01"}
    )
    assert second.status_code == 409, second.text
    assert second.json()["detail"] == "warehouse_code_taken"
    collision = await async_client.get(
        "/warehouses/resolve", headers=headers, params={"barcode": "A-01"}
    )
    assert collision.status_code == 200, collision.text
    assert collision.json()["type"] == "location"

    warehouse_code_location = await async_client.post(
        f"/warehouses/{body['id']}/locations",
        headers=headers,
        json={"code": "main"},
    )
    assert warehouse_code_location.status_code == 409, warehouse_code_location.text
    assert warehouse_code_location.json()["detail"] == "location_code_taken"

    rename_collision = await async_client.patch(
        f"/warehouses/{body['id']}/locations/{location.json()['id']}",
        headers=headers,
        json={"code": body["barcode"]},
    )
    assert rename_collision.status_code == 409, rename_collision.text
    assert rename_collision.json()["detail"] == "location_code_taken"
