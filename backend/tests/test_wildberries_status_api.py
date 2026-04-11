from __future__ import annotations

import time

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_wildberries_status_requires_auth(async_client: AsyncClient) -> None:
    r = await async_client.get("/integrations/wildberries/status")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_wildberries_status_forbidden_for_seller(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "WB Meta Co2",
            "slug": f"wb2-{suffix}",
            "admin_email": f"wb2-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    ah = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    s = await async_client.post("/sellers", headers=ah, json={"name": "S"})
    sid = s.json()["id"]
    await async_client.post(
        "/auth/seller-accounts",
        headers=ah,
        json={
            "seller_id": sid,
            "email": f"wb2-sl-{suffix}@example.com",
            "password": "password123",
        },
    )
    login = await async_client.post(
        "/auth/login",
        json={"email": f"wb2-sl-{suffix}@example.com", "password": "password123"},
    )
    sh = {"Authorization": f"Bearer {login.json()['access_token']}"}
    r = await async_client.get("/integrations/wildberries/status", headers=sh)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_wildberries_status_returns_bases(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "WB Meta Co",
            "slug": f"wb-{suffix}",
            "admin_email": f"wb-adm-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    h = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    r = await async_client.get("/integrations/wildberries/status", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert "content-api" in body["content_api_base"]
    assert "supplies-api" in body["supplies_api_base"]
    assert body["import_only"] is True
