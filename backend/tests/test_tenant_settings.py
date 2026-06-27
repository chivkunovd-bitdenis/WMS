from __future__ import annotations

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
    return reg.json()["access_token"]


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
