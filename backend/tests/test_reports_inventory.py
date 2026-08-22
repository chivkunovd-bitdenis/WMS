from __future__ import annotations

import time

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_reports_inventory_has_fixed_page_size_and_grouping(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    registered = await async_client.post("/auth/register", json={
        "organization_name": "Inventory reports", "slug": f"inventory-{suffix}",
        "admin_email": f"inventory-{suffix}@example.com", "password": "password123",
    })
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    params = {"date_from": "2026-08-01T00:00:00Z", "date_to": "2026-08-02T00:00:00Z"}
    response = await async_client.get("/reports/inventory", headers=headers, params=params)
    assert response.status_code == 200
    assert response.json()["group_by"] == "product"
    assert response.json()["page_size"] == 50

    response = await async_client.get("/reports/inventory", headers=headers,
        params={**params, "group_by": "operation"})
    assert response.status_code == 200
    assert response.json()["group_by"] == "operation"


@pytest.mark.asyncio
async def test_reports_inventory_rejects_unknown_grouping(async_client: AsyncClient) -> None:
    response = await async_client.get("/reports/inventory", params={
        "date_from": "2026-08-01T00:00:00Z", "date_to": "2026-08-02T00:00:00Z",
        "group_by": "warehouse",
    })
    assert response.status_code == 401
