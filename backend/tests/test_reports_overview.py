from __future__ import annotations

import time

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_reports_overview_rejects_period_longer_than_366_days(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    registered = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Reports",
            "slug": f"reports-{suffix}",
            "admin_email": f"reports-{suffix}@example.com",
            "password": "password123",
        },
    )
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    response = await async_client.get(
        "/reports/overview",
        headers=headers,
        params={"date_from": "2025-01-01T00:00:00Z", "date_to": "2026-01-03T00:00:00Z"},
    )
    assert response.status_code == 422
    assert "366" in response.json()["detail"]


@pytest.mark.asyncio
async def test_reports_overview_requires_authentication(async_client: AsyncClient) -> None:
    response = await async_client.get(
        "/reports/overview",
        params={"date_from": "2026-08-01T00:00:00Z", "date_to": "2026-08-02T00:00:00Z"},
    )
    assert response.status_code == 401
