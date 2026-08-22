from __future__ import annotations

import time

import pytest
from httpx import AsyncClient


async def _auth_headers(async_client: AsyncClient) -> dict[str, str]:
    suffix = str(int(time.time() * 1000))
    registered = await async_client.post("/auth/register", json={
        "organization_name": "CSV reports", "slug": f"csv-{suffix}",
        "admin_email": f"csv-{suffix}@example.com", "password": "password123",
    })
    return {"Authorization": f"Bearer {registered.json()['access_token']}"}


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
