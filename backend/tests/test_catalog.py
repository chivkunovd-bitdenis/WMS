from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_catalog_flow(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Cat Co",
            "slug": f"cat-flow-{suffix}",
            "admin_email": f"cat-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}

    wh = await async_client.post(
        "/warehouses",
        headers=h,
        json={"name": "Main", "code": "main-1"},
    )
    assert wh.status_code == 200, wh.text
    wid = wh.json()["id"]

    listed = await async_client.get("/warehouses", headers=h)
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["code"] == "main-1"

    loc = await async_client.post(
        f"/warehouses/{wid}/locations",
        headers=h,
        json={"code": "A-01"},
    )
    assert loc.status_code == 200, loc.text
    assert loc.json()["code"] == "A-01"

    locs = await async_client.get(f"/warehouses/{wid}/locations", headers=h)
    assert locs.status_code == 200
    assert len(locs.json()) == 1

    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Box",
            "sku_code": "SKU-1",
            "length_mm": 100,
            "width_mm": 200,
            "height_mm": 300,
        },
    )
    assert pr.status_code == 200, pr.text
    data = pr.json()
    assert data["sku_code"] == "SKU-1"
    assert data["volume_liters"] == pytest.approx(6.0)

    plist = await async_client.get("/products", headers=h)
    assert plist.status_code == 200
    assert len(plist.json()) == 1


@pytest.mark.asyncio
async def test_warehouse_duplicate_code(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "D Co",
            "slug": f"dup-wh-{suffix}",
            "admin_email": f"dup-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}

    r1 = await async_client.post(
        "/warehouses", headers=h, json={"name": "A", "code": "same"}
    )
    assert r1.status_code == 200
    r2 = await async_client.post(
        "/warehouses", headers=h, json={"name": "B", "code": "same"}
    )
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_catalog_endpoints_require_auth(async_client: AsyncClient) -> None:
    assert (await async_client.get("/warehouses")).status_code == 401
    assert (await async_client.get("/products")).status_code == 401
    assert (
        await async_client.post(
            "/warehouses",
            json={"name": "X", "code": "x1"},
        )
    ).status_code == 401


@pytest.mark.asyncio
async def test_list_locations_unknown_warehouse(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "U Co",
            "slug": f"unk-{suffix}",
            "admin_email": f"unk-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}
    bad = uuid.uuid4()
    r = await async_client.get(f"/warehouses/{bad}/locations", headers=h)
    assert r.status_code == 404
