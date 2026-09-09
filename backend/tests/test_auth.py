from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_login_me(async_client: AsyncClient) -> None:
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "FF Test",
            "slug": "ff-test",
            "admin_email": "admin@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    token = reg.json()["access_token"]
    assert token

    me = await async_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["email"] == "admin@example.com"
    assert body["organization_name"] == "FF Test"
    assert body["role"] == "fulfillment_admin"
    assert body["address_storage_enabled"] is True
    assert body["separate_marking_print_enabled"] is False

    login = await async_client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "password123"},
    )
    assert login.status_code == 200, login.text
    assert login.json()["access_token"]


@pytest.mark.asyncio
async def test_register_creates_default_warehouse(async_client: AsyncClient) -> None:
    """WMS-062: у новой организации сразу есть один «Основной» склад, и повторных нет."""
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "FF Warehouse Default",
            "slug": "ff-warehouse-default",
            "admin_email": "wh-default@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    token = reg.json()["access_token"]

    warehouses = await async_client.get(
        "/warehouses",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert warehouses.status_code == 200, warehouses.text
    items = warehouses.json()
    assert isinstance(items, list)
    names = [w["name"] for w in items]
    assert names == ["Основной"], names
    codes = [w["code"] for w in items]
    assert codes == ["main"], codes


@pytest.mark.asyncio
async def test_register_duplicate_slug(async_client: AsyncClient) -> None:
    payload = {
        "organization_name": "A",
        "slug": "same-slug",
        "admin_email": "a@example.com",
        "password": "password123",
    }
    r1 = await async_client.post("/auth/register", json=payload)
    assert r1.status_code == 200
    r2 = await async_client.post(
        "/auth/register",
        json={
            **payload,
            "admin_email": "b@example.com",
        },
    )
    assert r2.status_code == 409
