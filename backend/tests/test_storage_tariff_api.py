"""Tests for POST /operations/storage/tariffs — atom 08-storage finding-1 fix.

TC coverage:
  test_admin_creates_warehouse_tariff          — S-11-TC-002 happy path (common rate)
  test_admin_creates_tariff_with_seller_exception — S-11-TC-002 + atomicity invariant
  test_staff_inventory_cannot_set_tariff       — role gate (403)
"""
from __future__ import annotations

import time
import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.billing import BillingTariffVersion
from app.models.seller import Seller
from app.models.warehouse import Warehouse

FF_PERMISSION_DEFAULTS = {
    "settings": False,
    "mp_shipments": False,
    "reception": False,
    "cells": False,
    "inventory": False,
    "packaging": False,
    "shift_lead": False,
}


async def _register_admin(async_client: AsyncClient, suffix: str) -> dict[str, str]:
    reg = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Tariff Org {suffix}",
            "slug": f"tariff-org-{suffix}",
            "admin_email": f"admin-tariff-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert reg.status_code == 200, reg.text
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


async def _create_warehouse(
    async_client: AsyncClient, headers: dict[str, str], suffix: str, label: str = ""
) -> uuid.UUID:
    resp = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": f"WH {label} {suffix}", "code": f"wh-{label}-{suffix}"},
    )
    assert resp.status_code == 200, resp.text
    return uuid.UUID(resp.json()["id"])


async def _create_inventory_staff(
    async_client: AsyncClient,
    admin_headers: dict[str, str],
    suffix: str,
) -> dict[str, str]:
    """Create a fulfillment_staff account with only the `inventory` permission."""
    email = f"staff-inv-{suffix}@example.com"
    created = await async_client.post(
        "/auth/staff-accounts",
        headers=admin_headers,
        json={"email": email},
    )
    assert created.status_code == 201, created.text
    staff_id = created.json()["id"]

    await async_client.patch(
        f"/auth/staff-accounts/{staff_id}/permissions",
        headers=admin_headers,
        json={**FF_PERMISSION_DEFAULTS, "inventory": True},
    )

    await async_client.post(
        "/auth/set-initial-password",
        json={"email": email, "password": "password123"},
    )

    login = await async_client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


# ---------------------------------------------------------------------------
# TC-S11-001: admin creates a common warehouse tariff (no seller exception)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_creates_warehouse_tariff(async_client: AsyncClient) -> None:
    """POST warehouse tariff → 201, one billing_tariff_versions row, seller_id IS NULL."""
    suffix = str(time.time_ns())
    headers = await _register_admin(async_client, suffix)
    warehouse_id = await _create_warehouse(async_client, headers, suffix, "common")

    resp = await async_client.post(
        "/operations/storage/tariffs",
        headers=headers,
        json={
            "warehouse_id": str(warehouse_id),
            "amount": "5.00",
            "valid_from": "2026-09-01",
        },
    )
    assert resp.status_code == 201, resp.text

    body = resp.json()
    assert body["warehouse_tariff"]["seller_id"] is None
    assert body["warehouse_tariff"]["warehouse_id"] == str(warehouse_id)
    assert body["warehouse_tariff"]["amount"] == "5.00"
    assert body["warehouse_tariff"]["valid_from"] == "2026-09-01"
    assert body["seller_exception"] is None

    async with SessionLocal() as session:
        count = await session.scalar(
            select(func.count(BillingTariffVersion.id)).where(
                BillingTariffVersion.warehouse_id == warehouse_id,
                BillingTariffVersion.seller_id.is_(None),
                BillingTariffVersion.service_code == "storage_liter_day",
            )
        )
    assert count == 1


# ---------------------------------------------------------------------------
# TC-S11-002: seller exception — happy path + atomicity on second INSERT failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_creates_tariff_with_seller_exception(async_client: AsyncClient) -> None:
    """Two rows created atomically; when second INSERT fails, neither row is saved."""
    suffix = str(time.time_ns())
    headers = await _register_admin(async_client, suffix)
    warehouse_id = await _create_warehouse(async_client, headers, suffix, "ex")

    # Resolve tenant_id and create a seller directly via DB
    seller_id: uuid.UUID
    tenant_id: uuid.UUID
    async with SessionLocal() as session:
        wh = await session.get(Warehouse, warehouse_id)
        assert wh is not None
        tenant_id = wh.tenant_id
        seller = Seller(tenant_id=tenant_id, name=f"ExSeller {suffix}")
        session.add(seller)
        await session.commit()
        await session.refresh(seller)
        seller_id = seller.id

    # --- Happy path: POST warehouse tariff + seller exception → 201, 2 rows ---
    resp = await async_client.post(
        "/operations/storage/tariffs",
        headers=headers,
        json={
            "warehouse_id": str(warehouse_id),
            "amount": "5.00",
            "valid_from": "2026-09-01",
            "seller_exception": {
                "seller_id": str(seller_id),
                "amount": "3.00",
                "valid_from": "2026-09-01",
            },
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["warehouse_tariff"]["seller_id"] is None
    assert body["seller_exception"] is not None
    assert body["seller_exception"]["seller_id"] == str(seller_id)

    async with SessionLocal() as session:
        total = await session.scalar(
            select(func.count(BillingTariffVersion.id)).where(
                BillingTariffVersion.warehouse_id == warehouse_id,
                BillingTariffVersion.tenant_id == tenant_id,
                BillingTariffVersion.service_code == "storage_liter_day",
            )
        )
    assert total == 2

    # --- Atomicity: pre-seed a conflicting seller tariff, then POST again ---
    # Use a fresh warehouse so the warehouse tariff INSERT itself is not a conflict.
    warehouse2_id = await _create_warehouse(async_client, headers, suffix, "atom")

    async with SessionLocal() as session:
        seller2 = Seller(tenant_id=tenant_id, name=f"AtomSeller {suffix}")
        session.add(seller2)
        await session.flush()
        seller2_id = seller2.id
        # Pre-seed: seller tariff for 2026-10-01 — will conflict with the POST below.
        session.add(
            BillingTariffVersion(
                tenant_id=tenant_id,
                seller_id=seller2_id,
                warehouse_id=warehouse2_id,
                service_code="storage_liter_day",
                unit="liter_day",
                amount=Decimal("2.00"),
                valid_from=date(2026, 10, 1),
            )
        )
        await session.commit()

    # POST: warehouse tariff valid_from=2026-09-01 (no conflict) +
    #       seller exception valid_from=2026-10-01 (conflicts with pre-seeded row)
    conflict_resp = await async_client.post(
        "/operations/storage/tariffs",
        headers=headers,
        json={
            "warehouse_id": str(warehouse2_id),
            "amount": "5.00",
            "valid_from": "2026-09-01",
            "seller_exception": {
                "seller_id": str(seller2_id),
                "amount": "3.00",
                "valid_from": "2026-10-01",  # triggers UniqueConstraint
            },
        },
    )
    assert conflict_resp.status_code == 409, conflict_resp.text

    # Verify the warehouse tariff (first INSERT) was also rolled back.
    async with SessionLocal() as session:
        wh2_common_count = await session.scalar(
            select(func.count(BillingTariffVersion.id)).where(
                BillingTariffVersion.warehouse_id == warehouse2_id,
                BillingTariffVersion.seller_id.is_(None),
                BillingTariffVersion.service_code == "storage_liter_day",
                BillingTariffVersion.valid_from == date(2026, 9, 1),
            )
        )
    assert wh2_common_count == 0, (
        "Warehouse tariff must not persist when the seller exception INSERT failed"
    )


# ---------------------------------------------------------------------------
# TC-S11-003: fulfillment_staff with inventory permission → 403
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_staff_inventory_cannot_set_tariff(async_client: AsyncClient) -> None:
    """A fulfillment_staff user with `inventory` permission must not be able to create tariffs."""
    suffix = str(time.time_ns())
    admin_headers = await _register_admin(async_client, suffix)
    warehouse_id = await _create_warehouse(async_client, admin_headers, suffix, "auth")
    staff_headers = await _create_inventory_staff(async_client, admin_headers, suffix)

    resp = await async_client.post(
        "/operations/storage/tariffs",
        headers=staff_headers,
        json={
            "warehouse_id": str(warehouse_id),
            "amount": "5.00",
            "valid_from": "2026-09-01",
        },
    )
    assert resp.status_code == 403, resp.text
