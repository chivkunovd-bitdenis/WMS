from __future__ import annotations

import time

import pytest
from httpx import AsyncClient


async def _register(async_client: AsyncClient, suffix: str) -> dict[str, str]:
    response = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Ozon unload {suffix}",
            "slug": f"ozon-unload-{suffix}",
            "admin_email": f"ozon-unload-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _seller_headers(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    seller_id: str,
    suffix: str,
) -> dict[str, str]:
    email = f"ozon-seller-{suffix}@example.com"
    account = await async_client.post(
        "/auth/seller-accounts",
        headers=admin_headers,
        json={"seller_id": seller_id, "email": email, "password": "password123"},
    )
    assert account.status_code == 201, account.text
    login = await async_client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_ozon_unload_keeps_marketplace_scope_without_wb_warehouse(
    async_client: AsyncClient,
) -> None:
    """S-12: the same unload document exposes Ozon without borrowing WB fields."""
    suffix = str(int(time.time() * 1000))
    owner_headers = await _register(async_client, suffix)

    warehouse = await async_client.post(
        "/warehouses",
        headers=owner_headers,
        json={"name": "Ozon FF", "code": f"ozon-ff-{suffix}"},
    )
    assert warehouse.status_code == 200, warehouse.text
    seller = await async_client.post(
        "/sellers",
        headers=owner_headers,
        json={"name": "Ozon seller"},
    )
    assert seller.status_code == 201, seller.text

    created = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=owner_headers,
        json={
            "warehouse_id": warehouse.json()["id"],
            "seller_id": seller.json()["id"],
            "marketplace": "ozon",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["marketplace"] == "ozon"
    assert created.json()["wb_mp_warehouse_id"] is None

    request_id = created.json()["id"]
    plan = await async_client.post(
        f"/operations/marketplace-unload-requests/{request_id}/plan",
        headers=owner_headers,
    )
    assert plan.status_code == 409, plan.text
    assert plan.json()["detail"] == "no_lines"
    confirm = await async_client.post(
        f"/operations/marketplace-unload-requests/{request_id}/confirm",
        headers=owner_headers,
        json={},
    )
    assert confirm.status_code == 409, confirm.text
    assert confirm.json()["detail"] == "no_lines"
    ship = await async_client.post(
        f"/operations/marketplace-unload-requests/{request_id}/ship",
        headers=owner_headers,
        json={},
    )
    assert ship.status_code == 409, ship.text
    assert ship.json()["detail"] == "bad_status"
    detail = await async_client.get(
        f"/operations/marketplace-unload-requests/{request_id}",
        headers=owner_headers,
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["marketplace"] == "ozon"
    assert detail.json()["wb_mp_warehouse_id"] is None

    listed = await async_client.get(
        "/operations/marketplace-unload-requests",
        headers=owner_headers,
    )
    assert listed.status_code == 200, listed.text
    assert [(row["id"], row["marketplace"]) for row in listed.json()] == [
        (request_id, "ozon")
    ]

    other_headers = await _register(async_client, f"other-{suffix}")
    hidden = await async_client.get(
        f"/operations/marketplace-unload-requests/{request_id}",
        headers=other_headers,
    )
    assert hidden.status_code == 404, hidden.text

    other_seller = await async_client.post(
        "/sellers",
        headers=owner_headers,
        json={"name": "Other seller"},
    )
    assert other_seller.status_code == 201, other_seller.text
    other_seller_headers = await _seller_headers(
        async_client,
        owner_headers,
        other_seller.json()["id"],
        suffix,
    )
    hidden_same_tenant = await async_client.get(
        f"/operations/marketplace-unload-requests/{request_id}",
        headers=other_seller_headers,
    )
    assert hidden_same_tenant.status_code == 404, hidden_same_tenant.text

    wb_default = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=owner_headers,
        json={
            "warehouse_id": warehouse.json()["id"],
            "seller_id": seller.json()["id"],
        },
    )
    assert wb_default.status_code == 201, wb_default.text
    assert wb_default.json()["marketplace"] == "wb"

    invalid = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=owner_headers,
        json={
            "warehouse_id": warehouse.json()["id"],
            "seller_id": seller.json()["id"],
            "marketplace": "unknown",
        },
    )
    assert invalid.status_code == 422, invalid.text

    ozon_with_wb_warehouse = await async_client.post(
        "/operations/marketplace-unload-requests",
        headers=owner_headers,
        json={
            "warehouse_id": warehouse.json()["id"],
            "seller_id": seller.json()["id"],
            "marketplace": "ozon",
            "wb_mp_warehouse_id": 1,
        },
    )
    assert ozon_with_wb_warehouse.status_code == 422, ozon_with_wb_warehouse.text

    patch_wb_warehouse = await async_client.patch(
        f"/operations/marketplace-unload-requests/{request_id}",
        headers=owner_headers,
        json={"wb_mp_warehouse_id": 1},
    )
    assert patch_wb_warehouse.status_code == 422, patch_wb_warehouse.text
