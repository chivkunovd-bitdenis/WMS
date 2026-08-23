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

    async with SessionLocal() as session:
        stored_warehouse = await session.get(Warehouse, uuid.UUID(body["id"]))
        assert stored_warehouse is not None
        technical = Warehouse(
            tenant_id=stored_warehouse.tenant_id,
            name="FBS WB Legacy",
            code="fbs-wb-legacy",
            is_operational=False,
        )
        session.add(technical)
        await session.commit()

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
    assert second.status_code == 200, second.text
    collision = await async_client.get(
        "/warehouses/resolve", headers=headers, params={"barcode": "A-01"}
    )
    assert collision.status_code == 409
    assert collision.json()["detail"] == "barcode_ambiguous"
