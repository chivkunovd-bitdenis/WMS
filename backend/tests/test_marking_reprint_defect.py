from __future__ import annotations

import json
import uuid

import pytest
from httpx import AsyncClient
from test_packaging_tasks import _inventory_at_location, _register_admin


async def _seed_printed_code(
    async_client: AsyncClient,
) -> tuple[dict[str, str], str, str]:
    h = await _register_admin(async_client)
    suffix = uuid.uuid4().hex[:8]
    seller = await async_client.post(
        "/sellers",
        headers=h,
        json={"name": "Defect Seller", "email": f"s-{suffix}@example.com"},
    )
    assert seller.status_code == 201
    seller_id = seller.json()["id"]

    wh = await async_client.post(
        "/warehouses",
        headers=h,
        json={"name": "WH", "code": f"wh-{suffix}"},
    )
    assert wh.status_code == 200
    wh_id = wh.json()["id"]

    sku = f"SKU-DEF-{suffix}"
    product = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Defect Product",
            "sku_code": sku,
            "length_mm": 10,
            "width_mm": 10,
            "height_mm": 10,
            "seller_id": seller_id,
        },
    )
    assert product.status_code == 200
    product_id = product.json()["id"]

    await async_client.patch(
        f"/products/{product_id}/packaging-instructions",
        headers=h,
        json={"requires_honest_sign": True, "packaging_instructions": "ЧЗ"},
    )

    cis = f"01{'0' * 10}1234{'21'}{'B' * 20}0001"
    cis2 = f"01{'0' * 10}1234{'21'}{'B' * 20}0002"
    imp = await async_client.post(
        "/operations/marking-codes/import",
        headers=h,
        data={
            "seller_id": seller_id,
            "pools_json": json.dumps(
                [{"title": "Pool", "product_ids": [product_id]}],
            ),
        },
        files=[("files", ("codes.csv", f"cis\n{cis}\n{cis2}".encode(), "text/csv"))],
    )
    assert imp.status_code == 200, imp.text

    loc_id = await _inventory_at_location(
        async_client, h, warehouse_id=wh_id, product_id=product_id, qty=1, location_code=f"a-{suffix}"
    )

    task = await async_client.post(
        "/operations/packaging-tasks",
        headers=h,
        json={
            "warehouse_id": wh_id,
            "lines": [{"product_id": product_id, "storage_location_id": loc_id, "quantity": 1}],
        },
    )
    assert task.status_code == 201, task.text
    line_id = task.json()["lines"][0]["id"]

    printed = await async_client.post(
        f"/operations/marking-codes/packaging-lines/{line_id}/print",
        headers=h,
        json={"duplicate_copies": 1, "reprint": False},
    )
    assert printed.status_code == 200, printed.text
    code_id = (
        await async_client.get(
            f"/operations/marking-codes/packaging-task-lines/{line_id}/printed-codes",
            headers=h,
        )
    ).json()["codes"][0]["id"]

    return h, line_id, code_id


@pytest.mark.asyncio
async def test_defect_creates_pending_reprint_request(async_client: AsyncClient) -> None:
    admin_h, line_id, code_id = await _seed_printed_code(async_client)

    created = await async_client.post(
        f"/operations/marking-codes/codes/{code_id}/defect",
        headers=admin_h,
        json={"packaging_task_line_id": line_id, "reason": "Порвана этикетка"},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["status"] == "pending"
    assert body["code_id"] == code_id

    queue = await async_client.get(
        "/operations/marking-codes/reprint-requests",
        headers=admin_h,
    )
    assert queue.status_code == 200
    requests = queue.json()["requests"]
    assert len(requests) == 1
    assert requests[0]["reason"] == "Порвана этикетка"
    assert requests[0]["code_id"] == code_id

    dup = await async_client.post(
        f"/operations/marking-codes/codes/{code_id}/defect",
        headers=admin_h,
        json={"packaging_task_line_id": line_id},
    )
    assert dup.status_code == 422
    assert dup.json()["detail"] == "reprint_already_pending"


@pytest.mark.asyncio
async def test_defect_requires_packaging_access(async_client: AsyncClient) -> None:
    h = await _register_admin(async_client)
    staff_email = f"staff-nopack-{uuid.uuid4().hex[:8]}@example.com"
    created = await async_client.post(
        "/auth/staff-accounts",
        headers=h,
        json={"email": staff_email},
    )
    staff_id = created.json()["id"]
    await async_client.post(
        "/auth/set-initial-password",
        json={"email": staff_email, "password": "password123"},
    )
    await async_client.patch(
        f"/auth/staff-accounts/{staff_id}/permissions",
        headers=h,
        json={
            "settings": False,
            "mp_shipments": False,
            "reception": False,
            "cells": False,
            "inventory": False,
            "packaging": False,
            "shift_lead": True,
        },
    )
    login = await async_client.post(
        "/auth/login",
        json={"email": staff_email, "password": "password123"},
    )
    staff_h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    admin_h, line_id, code_id = await _seed_printed_code(async_client)
    forbidden = await async_client.post(
        f"/operations/marking-codes/codes/{code_id}/defect",
        headers=staff_h,
        json={"packaging_task_line_id": line_id},
    )
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_replace_reprint_request_clears_queue(async_client: AsyncClient) -> None:
    admin_h, line_id, code_id = await _seed_printed_code(async_client)

    created = await async_client.post(
        f"/operations/marking-codes/codes/{code_id}/defect",
        headers=admin_h,
        json={"packaging_task_line_id": line_id},
    )
    assert created.status_code == 200
    request_id = created.json()["request_id"]

    replaced = await async_client.post(
        f"/operations/marking-codes/reprint-requests/{request_id}/replace",
        headers=admin_h,
    )
    assert replaced.status_code == 200, replaced.text
    body = replaced.json()
    assert body["status"] == "approved"
    assert body["replacement_code_id"] is not None

    queue = await async_client.get(
        "/operations/marking-codes/reprint-requests",
        headers=admin_h,
    )
    assert queue.status_code == 200
    assert queue.json()["requests"] == []

