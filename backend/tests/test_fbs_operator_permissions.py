from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient


async def _staff_headers(
    client: AsyncClient,
    *,
    packaging: bool,
) -> tuple[dict[str, str], dict[str, str]]:
    suffix = str(time.time_ns())
    registration = await client.post(
        "/auth/register",
        json={
            "organization_name": "FBS operator access",
            "slug": f"fbs-operator-{suffix}",
            "admin_email": f"fbs-admin-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registration.status_code == 200, registration.text
    admin_headers = {
        "Authorization": f"Bearer {registration.json()['access_token']}"
    }

    email = f"fbs-staff-{suffix}@example.com"
    created = await client.post(
        "/auth/staff-accounts",
        headers=admin_headers,
        json={"email": email},
    )
    assert created.status_code == 201, created.text
    permissions = await client.patch(
        f"/auth/staff-accounts/{created.json()['id']}/permissions",
        headers=admin_headers,
        json={
            "settings": False,
            "mp_shipments": False,
            "reception": False,
            "cells": False,
            "inventory": False,
            "packaging": packaging,
        },
    )
    assert permissions.status_code == 200, permissions.text
    password = await client.post(
        "/auth/set-initial-password",
        json={"email": email, "password": "password123"},
    )
    assert password.status_code == 200, password.text
    login = await client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert login.status_code == 200, login.text
    staff_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    return admin_headers, staff_headers


@pytest.mark.asyncio
async def test_packaging_staff_can_use_fbs_operator_routes_but_not_admin_setup(
    async_client: AsyncClient,
) -> None:
    _, staff_headers = await _staff_headers(async_client, packaging=True)
    missing_id = uuid.uuid4()

    worklist = await async_client.get(
        "/operations/fbs-orders/worklist",
        headers=staff_headers,
    )
    assert worklist.status_code == 200, worklist.text
    assert worklist.json()["items"] == []

    # These missing-object responses prove that auth passed in every
    # operator-facing FBS router; an unauthorised role would receive 403 first.
    for method, path in (
        ("GET", f"/operations/fbs-supplies/{missing_id}/workspace"),
        ("POST", f"/operations/fbs-supplies/{missing_id}/retry-supply-qr"),
        ("GET", f"/operations/fbs-sellers/{missing_id}/warehouses"),
        ("GET", f"/operations/fbs-orders/{missing_id}/metadata"),
        ("GET", f"/operations/fbs-print-assets/{missing_id}/content"),
    ):
        response = await async_client.request(method, path, headers=staff_headers)
        assert response.status_code == 404, (path, response.text)

    admin_sync = await async_client.post(
        "/operations/fbs-orders/sync",
        headers=staff_headers,
        json={"seller_id": str(uuid.uuid4())},
    )
    assert admin_sync.status_code == 403


@pytest.mark.asyncio
async def test_staff_without_packaging_permission_cannot_open_fbs(
    async_client: AsyncClient,
) -> None:
    _, staff_headers = await _staff_headers(async_client, packaging=False)
    response = await async_client.get(
        "/operations/fbs-orders/worklist",
        headers=staff_headers,
    )
    assert response.status_code == 403
