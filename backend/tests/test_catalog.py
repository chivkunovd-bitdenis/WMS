from __future__ import annotations

import time
import uuid

import pytest
from httpx import AsyncClient


async def _register_catalog_admin(
    async_client: AsyncClient,
    suffix: str,
) -> dict[str, str]:
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Catalog Permissions Co",
            "slug": f"catalog-perms-{suffix}",
            "admin_email": f"catalog-admin-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


async def _create_ff_staff_headers(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    suffix: str,
    *,
    reception: bool = False,
    inventory: bool = False,
    shift_lead: bool = False,
) -> dict[str, str]:
    staff_email = f"catalog-staff-{suffix}@example.com"
    created = await async_client.post(
        "/auth/staff-accounts",
        headers=admin_headers,
        json={"email": staff_email},
    )
    assert created.status_code == 201, created.text
    patched = await async_client.patch(
        f"/auth/staff-accounts/{created.json()['id']}/permissions",
        headers=admin_headers,
        json={
            "settings": False,
            "mp_shipments": False,
            "reception": reception,
            "cells": False,
            "inventory": inventory,
            "packaging": False,
            "shift_lead": shift_lead,
        },
    )
    assert patched.status_code == 200, patched.text
    password = await async_client.post(
        "/auth/set-initial-password",
        json={"email": staff_email, "password": "password123"},
    )
    assert password.status_code == 200, password.text
    login = await async_client.post(
        "/auth/login",
        json={"email": staff_email, "password": "password123"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _create_catalog_product(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    suffix: str,
) -> str:
    response = await async_client.post(
        "/products",
        headers=admin_headers,
        json={
            "name": f"Measured Box {suffix}",
            "sku_code": f"MEASURED-{suffix}",
            "length_mm": 100,
            "width_mm": 200,
            "height_mm": 300,
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


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
    assert loc.json()["barcode"].startswith("LOC-")
    assert len(loc.json()["barcode"]) > 6

    locs = await async_client.get(f"/warehouses/{wid}/locations", headers=h)
    assert locs.status_code == 200
    assert len(locs.json()) == 2
    user_codes = [x for x in locs.json() if x["code"] != "__SORTING__"]
    assert len(user_codes) == 1
    assert user_codes[0]["barcode"] == loc.json()["barcode"]

    pr = await async_client.post(
        "/products",
        headers=h,
        json={
            "name": "Box",
            "sku_code": "SKU-1",
            "length_mm": 100,
            "width_mm": 200,
            "height_mm": 300,
            "weight_g": 750,
        },
    )
    assert pr.status_code == 200, pr.text
    data = pr.json()
    assert data["sku_code"] == "SKU-1"
    assert data["volume_liters"] == pytest.approx(6.0)
    assert data["weight_g"] == 750

    dims = await async_client.patch(
        f"/products/{data['id']}/dimensions",
        headers=h,
        json={"length_mm": 100, "width_mm": 100, "height_mm": 100, "weight_g": 900},
    )
    assert dims.status_code == 200, dims.text
    assert dims.json()["volume_liters"] == pytest.approx(1.0)
    assert dims.json()["weight_g"] == 900

    weight_only = await async_client.patch(
        f"/products/{data['id']}/dimensions",
        headers=h,
        json={"weight_g": 950},
    )
    assert weight_only.status_code == 200, weight_only.text
    assert weight_only.json()["volume_liters"] == pytest.approx(1.0)
    assert weight_only.json()["weight_g"] == 950

    plist = await async_client.get("/products", headers=h)
    assert plist.status_code == 200
    assert len(plist.json()) == 1


@pytest.mark.asyncio
async def test_reception_shift_lead_and_inventory_staff_can_update_product_dimensions(
    async_client: AsyncClient,
) -> None:
    suffix = str(time.time_ns())
    admin_headers = await _register_catalog_admin(async_client, suffix)
    product_id = await _create_catalog_product(async_client, admin_headers, suffix)

    no_perm_headers = await _create_ff_staff_headers(
        async_client,
        admin_headers,
        f"{suffix}-none",
    )
    forbidden = await async_client.patch(
        f"/products/{product_id}/dimensions",
        headers=no_perm_headers,
        json={"length_mm": 110, "width_mm": 120, "height_mm": 130},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == "forbidden"

    reception_headers = await _create_ff_staff_headers(
        async_client,
        admin_headers,
        f"{suffix}-reception",
        reception=True,
    )
    reception_update = await async_client.patch(
        f"/products/{product_id}/dimensions",
        headers=reception_headers,
        json={"length_mm": 100, "width_mm": 100, "height_mm": 100},
    )
    assert reception_update.status_code == 200, reception_update.text
    assert reception_update.json()["volume_liters"] == pytest.approx(1.0)

    shift_lead_headers = await _create_ff_staff_headers(
        async_client,
        admin_headers,
        f"{suffix}-shift-lead",
        shift_lead=True,
    )
    shift_lead_update = await async_client.patch(
        f"/products/{product_id}/dimensions",
        headers=shift_lead_headers,
        json={"length_mm": 200, "width_mm": 200, "height_mm": 200},
    )
    assert shift_lead_update.status_code == 200, shift_lead_update.text
    assert shift_lead_update.json()["volume_liters"] == pytest.approx(8.0)

    inventory_headers = await _create_ff_staff_headers(
        async_client,
        admin_headers,
        f"{suffix}-inventory",
        inventory=True,
    )
    inventory_update = await async_client.patch(
        f"/products/{product_id}/dimensions",
        headers=inventory_headers,
        json={"length_mm": 200, "width_mm": 200, "height_mm": 200},
    )
    assert inventory_update.status_code == 200, inventory_update.text
    assert inventory_update.json()["volume_liters"] == pytest.approx(8.0)


@pytest.mark.asyncio
async def test_staff_product_dimensions_validation_rejects_zero_and_partial_body(
    async_client: AsyncClient,
) -> None:
    suffix = str(time.time_ns())
    admin_headers = await _register_catalog_admin(async_client, suffix)
    product_id = await _create_catalog_product(async_client, admin_headers, suffix)
    inventory_headers = await _create_ff_staff_headers(
        async_client,
        admin_headers,
        f"{suffix}-inventory",
        inventory=True,
    )

    zero = await async_client.patch(
        f"/products/{product_id}/dimensions",
        headers=inventory_headers,
        json={"length_mm": 0, "width_mm": 100, "height_mm": 100},
    )
    assert zero.status_code == 422

    partial = await async_client.patch(
        f"/products/{product_id}/dimensions",
        headers=inventory_headers,
        json={"length_mm": 100, "width_mm": 100},
    )
    assert partial.status_code == 422


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
