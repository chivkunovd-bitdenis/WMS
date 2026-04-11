from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_seller_and_product_with_seller(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Sel Co",
            "slug": f"sel-{suffix}",
            "admin_email": f"sel-{suffix}@example.com",
            "password": "password123",
        },
    )
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}

    s = await async_client.post(
        "/sellers", headers=h, json={"name": "Seller One"}
    )
    assert s.status_code == 201, s.text
    sid = s.json()["id"]

    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Товар",
            "sku_code": f"SKU-{suffix}",
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": sid,
        },
    )
    assert pr.status_code == 200, pr.text
    assert pr.json()["seller_id"] == sid
    assert pr.json()["seller_name"] == "Seller One"

    listed = await async_client.get("/products", headers=h)
    row = next(x for x in listed.json() if x["sku_code"] == f"SKU-{suffix}")
    assert row["seller_name"] == "Seller One"


@pytest.mark.asyncio
async def test_product_unknown_seller(async_client: AsyncClient) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "X",
            "slug": f"x-{suffix}",
            "admin_email": f"x-{suffix}@example.com",
            "password": "password123",
        },
    )
    token = str(reg.json()["access_token"])
    h = {"Authorization": f"Bearer {token}"}
    bad = uuid.uuid4()
    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "T",
            "sku_code": f"S-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": str(bad),
        },
    )
    assert pr.status_code == 404
    assert pr.json()["detail"] == "seller_not_found"
