from __future__ import annotations

import time

import pytest
from httpx import AsyncClient
from inbound_box_intake_helpers import set_planned_boxes


async def _register_admin(async_client: AsyncClient) -> tuple[dict[str, str], str]:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Reception Staff",
            "slug": f"staff-inbound-{suffix}",
            "admin_email": f"adm-staff-inbound-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}, suffix


async def _create_staff(
    async_client: AsyncClient,
    admin_h: dict[str, str],
    *,
    suffix: str,
    reception: bool,
) -> dict[str, str]:
    staff_email = f"receiver-{suffix}-{int(reception)}@example.com"
    created = await async_client.post(
        "/auth/staff-accounts",
        headers=admin_h,
        json={"email": staff_email},
    )
    assert created.status_code == 201, created.text
    staff_id = created.json()["id"]
    patched = await async_client.patch(
        f"/auth/staff-accounts/{staff_id}/permissions",
        headers=admin_h,
        json={
            "settings": False,
            "mp_shipments": False,
            "reception": reception,
            "cells": False,
            "inventory": False,
            "packaging": False,
        },
    )
    assert patched.status_code == 200, patched.text
    set_pw = await async_client.post(
        "/auth/set-initial-password",
        json={"email": staff_email, "password": "password123"},
    )
    assert set_pw.status_code == 200, set_pw.text
    login = await async_client.post(
        "/auth/login",
        json={"email": staff_email, "password": "password123"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest.mark.asyncio
async def test_staff_with_reception_permission_can_create_and_submit_inbound_draft(
    async_client: AsyncClient,
) -> None:
    admin_h, suffix = await _register_admin(async_client)
    wh = await async_client.post(
        "/warehouses",
        headers=admin_h,
        json={"name": "Reception WH", "code": f"recv-{suffix}"},
    )
    assert wh.status_code == 200, wh.text
    wid = wh.json()["id"]
    product = await async_client.post(
        "/products",
        headers=admin_h,
        json={
            "name": "Reception product",
            "sku_code": f"RECV-{suffix}",
            "length_mm": 1,
            "width_mm": 1,
            "height_mm": 1,
        },
    )
    assert product.status_code == 200, product.text
    pid = product.json()["id"]

    staff_h = await _create_staff(
        async_client, admin_h, suffix=suffix, reception=True
    )
    base = "/operations/inbound-intake-requests"
    created = await async_client.post(base, headers=staff_h, json={"warehouse_id": wid})
    assert created.status_code == 201, created.text
    rid = created.json()["id"]
    assert created.json()["seller_id"] is None
    assert created.json()["status"] == "draft"

    line = await async_client.post(
        f"{base}/{rid}/lines",
        headers=staff_h,
        json={"product_id": pid, "expected_qty": 2},
    )
    assert line.status_code == 201, line.text
    line_id = line.json()["id"]

    patched = await async_client.patch(
        f"{base}/{rid}/lines/{line_id}/expected",
        headers=staff_h,
        json={"expected_qty": 3},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["expected_qty"] == 3

    await set_planned_boxes(async_client, base, rid, staff_h)
    submitted = await async_client.post(f"{base}/{rid}/submit", headers=staff_h)
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted"


@pytest.mark.asyncio
async def test_staff_without_reception_permission_cannot_create_inbound_draft(
    async_client: AsyncClient,
) -> None:
    admin_h, suffix = await _register_admin(async_client)
    wh = await async_client.post(
        "/warehouses",
        headers=admin_h,
        json={"name": "No Reception WH", "code": f"no-recv-{suffix}"},
    )
    assert wh.status_code == 200, wh.text
    staff_h = await _create_staff(
        async_client, admin_h, suffix=f"{suffix}-no", reception=False
    )

    denied = await async_client.post(
        "/operations/inbound-intake-requests",
        headers=staff_h,
        json={"warehouse_id": wh.json()["id"]},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "forbidden"
