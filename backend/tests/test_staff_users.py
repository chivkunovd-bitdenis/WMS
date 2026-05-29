from __future__ import annotations

import time

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_admin_creates_staff_user_first_login_and_permissions(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Staff Co",
            "slug": f"staff-{suffix}",
            "admin_email": f"adm-staff-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    admin_tok = str(reg.json()["access_token"])
    ah = {"Authorization": f"Bearer {admin_tok}"}

    staff_email = f"staff-{suffix}@example.com"
    created = await async_client.post(
        "/auth/staff-accounts",
        headers=ah,
        json={"email": staff_email},
    )
    assert created.status_code == 201, created.text
    staff_id = created.json()["id"]
    assert created.json()["must_set_password"] is True
    assert created.json()["permissions"]["reception"] is False

    listed = await async_client.get("/auth/staff-accounts", headers=ah)
    assert listed.status_code == 200
    assert any(row["email"] == staff_email for row in listed.json())

    patched = await async_client.patch(
        f"/auth/staff-accounts/{staff_id}/permissions",
        headers=ah,
        json={
            "settings": False,
            "mp_shipments": True,
            "reception": True,
            "cells": False,
            "inventory": False,
        },
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["permissions"]["mp_shipments"] is True
    assert patched.json()["permissions"]["reception"] is True

    need_pw = await async_client.post(
        "/auth/login",
        json={"email": staff_email, "password": ""},
    )
    assert need_pw.status_code == 403
    assert need_pw.json()["detail"] == "password_setup_required"

    set_pw = await async_client.post(
        "/auth/set-initial-password",
        json={"email": staff_email, "password": "password123"},
    )
    assert set_pw.status_code == 200, set_pw.text

    login = await async_client.post(
        "/auth/login",
        json={"email": staff_email, "password": "password123"},
    )
    assert login.status_code == 200
    sh = {"Authorization": f"Bearer {login.json()['access_token']}"}

    me = await async_client.get("/auth/me", headers=sh)
    assert me.status_code == 200
    body = me.json()
    assert body["role"] == "fulfillment_staff"
    assert body["permissions"]["reception"] is True
    assert body["permissions"]["mp_shipments"] is True
    assert body["permissions"]["cells"] is False

    forbidden_staff_mgmt = await async_client.post(
        "/auth/staff-accounts",
        headers=sh,
        json={"email": f"other-{suffix}@example.com"},
    )
    assert forbidden_staff_mgmt.status_code == 403
