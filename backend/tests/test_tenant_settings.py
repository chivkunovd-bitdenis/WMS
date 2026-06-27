from __future__ import annotations

import time

import pytest
from httpx import AsyncClient


async def _register_admin(async_client: AsyncClient, slug: str) -> str:
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Tenant Settings FF",
            "slug": slug,
            "admin_email": f"admin-{slug}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    return str(reg.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_me_includes_address_storage_enabled_default_true(
    async_client: AsyncClient,
) -> None:
    token = await _register_admin(async_client, "tenant-settings-me")
    me = await async_client.get("/auth/me", headers=_auth(token))
    assert me.status_code == 200, me.text
    assert me.json()["address_storage_enabled"] is True


@pytest.mark.asyncio
async def test_tenant_settings_get_and_patch(async_client: AsyncClient) -> None:
    token = await _register_admin(async_client, "tenant-settings-patch")
    headers = _auth(token)

    get0 = await async_client.get("/tenant/settings", headers=headers)
    assert get0.status_code == 200, get0.text
    assert get0.json()["address_storage_enabled"] is True

    patch = await async_client.patch(
        "/tenant/settings",
        headers=headers,
        json={"address_storage_enabled": False},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["address_storage_enabled"] is False

    me = await async_client.get("/auth/me", headers=headers)
    assert me.json()["address_storage_enabled"] is False

    get1 = await async_client.get("/tenant/settings", headers=headers)
    assert get1.json()["address_storage_enabled"] is False


@pytest.mark.asyncio
async def test_tenant_settings_forbidden_for_staff(async_client: AsyncClient) -> None:
    admin_token = await _register_admin(async_client, "tenant-settings-staff")
    admin_headers = _auth(admin_token)

    create_staff = await async_client.post(
        "/auth/staff-accounts",
        headers=admin_headers,
        json={"email": "staff-tenant-settings@example.com"},
    )
    assert create_staff.status_code == 201, create_staff.text

    need_pw = await async_client.post(
        "/auth/login",
        json={"email": "staff-tenant-settings@example.com", "password": ""},
    )
    assert need_pw.status_code == 403
    assert need_pw.json()["detail"] == "password_setup_required"

    setup = await async_client.post(
        "/auth/set-initial-password",
        json={
            "email": "staff-tenant-settings@example.com",
            "password": "password123",
        },
    )
    assert setup.status_code == 200, setup.text

    login = await async_client.post(
        "/auth/login",
        json={"email": "staff-tenant-settings@example.com", "password": "password123"},
    )
    assert login.status_code == 200, login.text
    staff_token = login.json()["access_token"]

    denied = await async_client.patch(
        "/tenant/settings",
        headers=_auth(staff_token),
        json={"address_storage_enabled": False},
    )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_disable_address_storage_migrates_stock_to_sorting(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REV-FIX-003 / DEC-019: PATCH false переносит остатки из ячеек на зону сортировки."""
    from test_marketplace_unload_and_discrepancy_acts import (
        _post_inventory,
        _seller_wb_mp_warehouse,
    )

    token = await _register_admin(async_client, "tenant-settings-migrate")
    headers = _auth(token)
    suffix = str(int(time.time() * 1000))
    wh = await async_client.post(
        "/warehouses", headers=headers, json={"name": "W", "code": f"w-mig-{suffix}"}
    )
    assert wh.status_code == 200, wh.text
    wid = wh.json()["id"]
    sid, _ = await _seller_wb_mp_warehouse(async_client, headers, monkeypatch)
    pr = await async_client.post(
        "/products",
        headers=headers,
        json={
            "name": "P",
            "sku_code": f"mig-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
            "seller_id": sid,
        },
    )
    assert pr.status_code in (200, 201), pr.text
    pid = pr.json()["id"]
    loc_id = await _post_inventory(
        async_client,
        headers,
        warehouse_id=wid,
        product_id=pid,
        qty=5,
        location_code="MIG-LOC",
    )

    before = await async_client.get(
        "/operations/inventory-balances",
        headers=headers,
        params={"storage_location_id": loc_id},
    )
    assert before.status_code == 200, before.text
    assert before.json()[0]["quantity"] == 5

    patch = await async_client.patch(
        "/tenant/settings",
        headers=headers,
        json={"address_storage_enabled": False},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["address_storage_enabled"] is False

    after_cell = await async_client.get(
        "/operations/inventory-balances",
        headers=headers,
        params={"storage_location_id": loc_id},
    )
    assert after_cell.status_code == 200, after_cell.text
    assert sum(row["quantity"] for row in after_cell.json()) == 0

    locs = await async_client.get(f"/warehouses/{wid}/locations", headers=headers)
    assert locs.status_code == 200, locs.text
    sorting = next(row for row in locs.json() if row["code"] == "__SORTING__")
    after_sort = await async_client.get(
        "/operations/inventory-balances",
        headers=headers,
        params={"storage_location_id": sorting["id"]},
    )
    assert after_sort.status_code == 200, after_sort.text
    assert sum(row["quantity"] for row in after_sort.json()) == 5
