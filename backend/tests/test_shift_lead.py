from __future__ import annotations

import time

import pytest
from httpx import AsyncClient
from test_marking_reprint_defect import _seed_printed_code


async def _register_admin(async_client: AsyncClient) -> tuple[str, dict[str, str]]:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Shift Lead Co",
            "slug": f"shift-lead-{suffix}",
            "admin_email": f"adm-shift-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200
    token = str(reg.json()["access_token"])
    return suffix, {"Authorization": f"Bearer {token}"}


async def _create_staff_with_login(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    suffix: str,
    *,
    shift_lead: bool,
) -> dict[str, str]:
    staff_email = f"staff-shift-{suffix}@example.com"
    created = await async_client.post(
        "/auth/staff-accounts",
        headers=admin_headers,
        json={"email": staff_email},
    )
    assert created.status_code == 201, created.text
    staff_id = created.json()["id"]

    patched = await async_client.patch(
        f"/auth/staff-accounts/{staff_id}/permissions",
        headers=admin_headers,
        json={
            "settings": False,
            "mp_shipments": False,
            "reception": False,
            "cells": False,
            "inventory": False,
            "packaging": True,
            "shift_lead": shift_lead,
        },
    )
    assert patched.status_code == 200, patched.text

    set_pw = await async_client.post(
        "/auth/set-initial-password",
        json={"email": staff_email, "password": "password123"},
    )
    assert set_pw.status_code == 200

    login = await async_client.post(
        "/auth/login",
        json={"email": staff_email, "password": "password123"},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_reprint_requests_require_shift_lead(async_client: AsyncClient) -> None:
    suffix, admin_headers = await _register_admin(async_client)

    no_perm = await _create_staff_with_login(
        async_client, admin_headers, suffix, shift_lead=False
    )
    forbidden = await async_client.get(
        "/operations/marking-codes/reprint-requests",
        headers=no_perm,
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "forbidden"

    with_perm = await _create_staff_with_login(
        async_client, admin_headers, f"{suffix}-lead", shift_lead=True
    )
    allowed = await async_client.get(
        "/operations/marking-codes/reprint-requests",
        headers=with_perm,
    )
    assert allowed.status_code == 200
    assert allowed.json()["requests"] == []

    admin_ok = await async_client.get(
        "/operations/marking-codes/reprint-requests",
        headers=admin_headers,
    )
    assert admin_ok.status_code == 200


@pytest.mark.asyncio
async def test_reprint_mutations_require_shift_lead(async_client: AsyncClient) -> None:
    """TC-NEW CZ-H10: replace/approve/reject reprint requests require shift_lead."""
    admin_h, line_id, code_id = await _seed_printed_code(async_client)
    suffix = str(int(time.time() * 1000))
    no_perm = await _create_staff_with_login(
        async_client, admin_h, suffix, shift_lead=False
    )

    created = await async_client.post(
        f"/operations/marking-codes/codes/{code_id}/defect",
        headers=admin_h,
        json={"packaging_task_line_id": line_id},
    )
    assert created.status_code == 200, created.text
    request_id = created.json()["request_id"]

    replace = await async_client.post(
        f"/operations/marking-codes/reprint-requests/{request_id}/replace",
        headers=no_perm,
    )
    assert replace.status_code == 403
    assert replace.json()["detail"] == "forbidden"

    approve = await async_client.post(
        f"/operations/marking-codes/reprint-requests/{request_id}/approve-reprint",
        headers=no_perm,
    )
    assert approve.status_code == 403
    assert approve.json()["detail"] == "forbidden"

    reject = await async_client.post(
        f"/operations/marking-codes/reprint-requests/{request_id}/reject",
        headers=no_perm,
        json={"reason": "test"},
    )
    assert reject.status_code == 403
    assert reject.json()["detail"] == "forbidden"
