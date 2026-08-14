from __future__ import annotations

import time

import pytest
from httpx import AsyncClient

FF_PERMISSION_DEFAULTS = {
    "settings": False,
    "mp_shipments": False,
    "reception": False,
    "cells": False,
    "inventory": False,
    "packaging": False,
    "shift_lead": False,
}


async def _create_ff_staff(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    suffix: str,
    label: str,
    permissions: dict[str, bool],
) -> tuple[dict[str, str], dict]:
    staff_email = f"staff-{label}-{suffix}@example.com"
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
        json={**FF_PERMISSION_DEFAULTS, **permissions},
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
    return {"Authorization": f"Bearer {login.json()['access_token']}"}, patched.json()


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
            "packaging": False,
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


@pytest.mark.asyncio
async def test_ff_staff_rights_fail_closed_by_work_block(
    async_client: AsyncClient,
) -> None:
    suffix = str(int(time.time() * 1000))
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Staff Rights Co",
            "slug": f"staff-rights-{suffix}",
            "admin_email": f"adm-staff-rights-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    admin_headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    reception_headers, _ = await _create_ff_staff(
        async_client,
        admin_headers,
        suffix,
        "reception",
        {"reception": True},
    )
    reception_products = await async_client.get("/products", headers=reception_headers)
    assert reception_products.status_code == 200, reception_products.text
    reception_inventory = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=reception_headers,
    )
    assert reception_inventory.status_code == 403
    reception_shipments = await async_client.get(
        "/operations/marketplace-unload-requests",
        headers=reception_headers,
    )
    assert reception_shipments.status_code == 403
    reception_staff = await async_client.get(
        "/auth/staff-accounts",
        headers=reception_headers,
    )
    assert reception_staff.status_code == 403

    shipments_headers, _ = await _create_ff_staff(
        async_client,
        admin_headers,
        suffix,
        "shipments",
        {"mp_shipments": True, "packaging": True, "shift_lead": True},
    )
    shipments_list = await async_client.get(
        "/operations/marketplace-unload-requests",
        headers=shipments_headers,
    )
    assert shipments_list.status_code == 200, shipments_list.text
    fbs_worklist = await async_client.get(
        "/operations/fbs-orders/worklist",
        headers=shipments_headers,
    )
    assert fbs_worklist.status_code == 200, fbs_worklist.text
    admin_fbs_sync = await async_client.post(
        "/operations/fbs-orders/sync",
        headers=shipments_headers,
        json={"seller_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert admin_fbs_sync.status_code == 403
    shipments_inventory = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=shipments_headers,
    )
    assert shipments_inventory.status_code == 403
    shipments_staff = await async_client.get(
        "/auth/staff-accounts",
        headers=shipments_headers,
    )
    assert shipments_staff.status_code == 403

    mp_only_headers, _ = await _create_ff_staff(
        async_client,
        admin_headers,
        suffix,
        "mp-only",
        {"mp_shipments": True},
    )
    mp_only_shipments = await async_client.get(
        "/operations/marketplace-unload-requests",
        headers=mp_only_headers,
    )
    assert mp_only_shipments.status_code == 200, mp_only_shipments.text
    mp_only_fbs = await async_client.get(
        "/operations/fbs-orders/worklist",
        headers=mp_only_headers,
    )
    assert mp_only_fbs.status_code == 403
    mp_only_packaging = await async_client.get(
        "/operations/packaging-tasks",
        headers=mp_only_headers,
    )
    assert mp_only_packaging.status_code == 403

    packaging_only_headers, _ = await _create_ff_staff(
        async_client,
        admin_headers,
        suffix,
        "packaging-only",
        {"packaging": True},
    )
    packaging_only_shipments = await async_client.get(
        "/operations/marketplace-unload-requests",
        headers=packaging_only_headers,
    )
    assert packaging_only_shipments.status_code == 403
    packaging_only_fbs = await async_client.get(
        "/operations/fbs-orders/worklist",
        headers=packaging_only_headers,
    )
    assert packaging_only_fbs.status_code == 200, packaging_only_fbs.text
    packaging_only_tasks = await async_client.get(
        "/operations/packaging-tasks",
        headers=packaging_only_headers,
    )
    assert packaging_only_tasks.status_code == 200, packaging_only_tasks.text
    packaging_only_reprints = await async_client.get(
        "/operations/marking-codes/reprint-requests",
        headers=packaging_only_headers,
    )
    assert packaging_only_reprints.status_code == 403

    shift_lead_headers, _ = await _create_ff_staff(
        async_client,
        admin_headers,
        suffix,
        "shift-lead",
        {"shift_lead": True},
    )
    shift_lead_reprints = await async_client.get(
        "/operations/marking-codes/reprint-requests",
        headers=shift_lead_headers,
    )
    assert shift_lead_reprints.status_code == 200, shift_lead_reprints.text
    shift_lead_shipments = await async_client.get(
        "/operations/marketplace-unload-requests",
        headers=shift_lead_headers,
    )
    assert shift_lead_shipments.status_code == 403
    shift_lead_fbs = await async_client.get(
        "/operations/fbs-orders/worklist",
        headers=shift_lead_headers,
    )
    assert shift_lead_fbs.status_code == 403

    cells_headers, _ = await _create_ff_staff(
        async_client,
        admin_headers,
        suffix,
        "cells",
        {"cells": True, "inventory": True},
    )
    cells_products = await async_client.get("/products", headers=cells_headers)
    assert cells_products.status_code == 200, cells_products.text
    ff_catalog = await async_client.get("/products/ff-catalog", headers=cells_headers)
    assert ff_catalog.status_code == 200, ff_catalog.text
    ff_catalog_seller_filter = await async_client.get(
        "/products/ff-catalog?seller_id=00000000-0000-0000-0000-000000000000",
        headers=cells_headers,
    )
    assert ff_catalog_seller_filter.status_code == 403
    cells_inventory = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=cells_headers,
    )
    assert cells_inventory.status_code == 200, cells_inventory.text
    run_snapshot = await async_client.post(
        "/operations/inventory-balances/monthly-snapshots/run",
        headers=cells_headers,
        json={"month": "2026-08-01"},
    )
    assert run_snapshot.status_code == 403
    cells_shipments = await async_client.get(
        "/operations/marketplace-unload-requests",
        headers=cells_headers,
    )
    assert cells_shipments.status_code == 403

    inventory_only_headers, _ = await _create_ff_staff(
        async_client,
        admin_headers,
        suffix,
        "inventory-only",
        {"inventory": True},
    )
    inventory_only_catalog = await async_client.get(
        "/products/ff-catalog",
        headers=inventory_only_headers,
    )
    assert inventory_only_catalog.status_code == 200, inventory_only_catalog.text
    inventory_only_seller_filter = await async_client.get(
        "/products/ff-catalog?seller_id=00000000-0000-0000-0000-000000000000",
        headers=inventory_only_headers,
    )
    assert inventory_only_seller_filter.status_code == 403
    inventory_only_snapshots = await async_client.get(
        "/operations/inventory-balances/monthly-snapshots?month=2026-08-01",
        headers=inventory_only_headers,
    )
    assert inventory_only_snapshots.status_code == 200, inventory_only_snapshots.text
    inventory_only_location = await async_client.post(
        "/warehouses/00000000-0000-0000-0000-000000000000/locations",
        headers=inventory_only_headers,
        json={"code": "NO-CELL-MANAGE"},
    )
    assert inventory_only_location.status_code == 403
    inventory_only_snapshot = await async_client.post(
        "/operations/inventory-balances/monthly-snapshots/run",
        headers=inventory_only_headers,
        json={"month": "2026-08-01"},
    )
    assert inventory_only_snapshot.status_code == 403

    settings_headers, _ = await _create_ff_staff(
        async_client,
        admin_headers,
        suffix,
        "settings",
        {"settings": True},
    )
    staff_list = await async_client.get(
        "/auth/staff-accounts",
        headers=settings_headers,
    )
    assert staff_list.status_code == 200, staff_list.text
    settings_rows = staff_list.json()
    assert settings_rows
    assert all("packaging_rate_rub" not in row for row in settings_rows)
    assert all("packaging_billing" not in row for row in settings_rows)
    settings_rate_patch = await async_client.patch(
        f"/auth/staff-accounts/{settings_rows[0]['id']}/packaging-rate",
        headers=settings_headers,
        json={"rate_rub": "12.50"},
    )
    assert settings_rate_patch.status_code == 403
    settings_products = await async_client.get("/products", headers=settings_headers)
    assert settings_products.status_code == 403
    settings_inventory = await async_client.get(
        "/operations/inventory-balances/summary",
        headers=settings_headers,
    )
    assert settings_inventory.status_code == 403
    settings_shipments = await async_client.get(
        "/operations/marketplace-unload-requests",
        headers=settings_headers,
    )
    assert settings_shipments.status_code == 403
