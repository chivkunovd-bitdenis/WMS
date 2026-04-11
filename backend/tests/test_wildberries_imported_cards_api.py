from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_wb_imported_cards_get_requires_auth(async_client: AsyncClient) -> None:
    r = await async_client.get(
        f"/integrations/wildberries/sellers/{uuid.uuid4()}/imported-cards",
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_wb_imported_cards_not_found_seller(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "WB IC Co",
            "slug": f"wic-{suffix}",
            "admin_email": f"wic-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    missing = uuid.UUID("00000000-0000-4000-8000-000000000077")
    r = await async_client.get(
        f"/integrations/wildberries/sellers/{missing}/imported-cards",
        headers=h,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_wb_imported_cards_empty_for_new_seller(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "WB IC Co2",
            "slug": f"wic2-{suffix}",
            "admin_email": f"wic2-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    s = await async_client.post("/sellers", headers=h, json={"name": "S"})
    sid = s.json()["id"]
    r = await async_client.get(
        f"/integrations/wildberries/sellers/{sid}/imported-cards",
        headers=h,
    )
    assert r.status_code == 200
    assert r.json() == []
