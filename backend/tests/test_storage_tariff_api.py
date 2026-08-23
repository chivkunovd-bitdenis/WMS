"""Tests for POST /operations/storage/tariffs — atom 08-storage finding-1 fix.

TC coverage:
  test_admin_creates_warehouse_tariff          — S-11-TC-002 happy path (common rate)
  test_admin_creates_tariff_with_seller_exception — S-11-TC-002 + atomicity invariant
  test_staff_inventory_cannot_set_tariff       — role gate (403)
  test_tariff_scope_must_belong_to_tenant_and_operational_warehouse
                                               — S-11-TC-002/S-11-TC-020 tenant and warehouse scope
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta
from datetime import time as datetime_time
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.billing import BillingTariffVersion
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_measurement import StorageMeasurement
from app.models.storage_statement import StorageStatement
from app.models.warehouse import Warehouse
from app.services.sorting_location_service import get_or_create_sorting_location
from app.services.storage_measurement_service import MOSCOW, month_bounds

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
    valid_from = datetime.now(MOSCOW).date()

    resp = await async_client.post(
        "/operations/storage/tariffs",
        headers=headers,
        json={
            "warehouse_id": str(warehouse_id),
            "amount": "5.00",
            "valid_from": valid_from.isoformat(),
        },
    )
    assert resp.status_code == 201, resp.text

    body = resp.json()
    assert body["warehouse_tariff"]["seller_id"] is None
    assert body["warehouse_tariff"]["warehouse_id"] == str(warehouse_id)
    assert body["warehouse_tariff"]["amount"] == "5.00"
    assert body["warehouse_tariff"]["valid_from"] == valid_from.isoformat()
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
    today = datetime.now(MOSCOW).date()
    warehouse_valid_from = today + timedelta(days=1)
    seller_valid_from = today + timedelta(days=2)

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
            "valid_from": warehouse_valid_from.isoformat(),
            "seller_exception": {
                "seller_id": str(seller_id),
                "amount": "3.00",
                "valid_from": seller_valid_from.isoformat(),
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
    atomic_warehouse_valid_from = today + timedelta(days=3)
    atomic_seller_valid_from = today + timedelta(days=4)

    async with SessionLocal() as session:
        seller2 = Seller(tenant_id=tenant_id, name=f"AtomSeller {suffix}")
        session.add(seller2)
        await session.flush()
        seller2_id = seller2.id
        # Pre-seed a dated seller tariff that will conflict with the POST below.
        session.add(
            BillingTariffVersion(
                tenant_id=tenant_id,
                seller_id=seller2_id,
                warehouse_id=warehouse2_id,
                service_code="storage_liter_day",
                unit="liter_day",
                amount=Decimal("2.00"),
                valid_from=atomic_seller_valid_from,
            )
        )
        await session.commit()

    # POST: the warehouse date is free, while the seller exception conflicts.
    conflict_resp = await async_client.post(
        "/operations/storage/tariffs",
        headers=headers,
        json={
            "warehouse_id": str(warehouse2_id),
            "amount": "5.00",
            "valid_from": atomic_warehouse_valid_from.isoformat(),
            "seller_exception": {
                "seller_id": str(seller2_id),
                "amount": "3.00",
                "valid_from": atomic_seller_valid_from.isoformat(),
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
                BillingTariffVersion.valid_from == atomic_warehouse_valid_from,
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
    valid_from = datetime.now(MOSCOW).date().isoformat()

    resp = await async_client.post(
        "/operations/storage/tariffs",
        headers=staff_headers,
        json={
            "warehouse_id": str(warehouse_id),
            "amount": "5.00",
            "valid_from": valid_from,
        },
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target", "amount"),
    [
        ("warehouse", "0"),
        ("warehouse", "-0.01"),
        ("seller_exception", "0"),
        ("seller_exception", "-0.01"),
    ],
)
async def test_tariff_amount_must_be_positive(
    async_client: AsyncClient, target: str, amount: str
) -> None:
    """The API rejects non-positive common and seller rates before any write."""
    suffix = str(time.time_ns())
    headers = await _register_admin(async_client, suffix)
    warehouse_id = await _create_warehouse(async_client, headers, suffix, "amount")
    today = datetime.now(MOSCOW).date().isoformat()
    payload: dict[str, object] = {
        "warehouse_id": str(warehouse_id),
        "amount": amount if target == "warehouse" else "5.00",
        "valid_from": today,
    }
    expected_location = ["body", "amount"]
    if target == "seller_exception":
        async with SessionLocal() as session:
            warehouse = await session.get(Warehouse, warehouse_id)
            assert warehouse is not None
            seller = Seller(tenant_id=warehouse.tenant_id, name=f"Amount seller {suffix}")
            session.add(seller)
            await session.commit()
            await session.refresh(seller)
        payload["seller_exception"] = {
            "seller_id": str(seller.id),
            "amount": amount,
            "valid_from": today,
        }
        expected_location = ["body", "seller_exception", "amount"]

    response = await async_client.post(
        "/operations/storage/tariffs",
        headers=headers,
        json=payload,
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["loc"] == expected_location
    async with SessionLocal() as session:
        count = await session.scalar(
            select(func.count(BillingTariffVersion.id)).where(
                BillingTariffVersion.warehouse_id == warehouse_id
            )
        )
    assert count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["warehouse", "seller_exception"])
async def test_tariff_valid_from_cannot_be_in_the_past(
    async_client: AsyncClient, target: str
) -> None:
    """Neither common nor seller storage rates can start before Moscow today."""
    suffix = str(time.time_ns())
    headers = await _register_admin(async_client, suffix)
    warehouse_id = await _create_warehouse(async_client, headers, suffix, "past")
    today = datetime.now(MOSCOW).date()
    payload: dict[str, object] = {
        "warehouse_id": str(warehouse_id),
        "amount": "5.00",
        "valid_from": (
            today - timedelta(days=1) if target == "warehouse" else today
        ).isoformat(),
    }
    if target == "seller_exception":
        async with SessionLocal() as session:
            warehouse = await session.get(Warehouse, warehouse_id)
            assert warehouse is not None
            seller = Seller(tenant_id=warehouse.tenant_id, name=f"Past seller {suffix}")
            session.add(seller)
            await session.commit()
            await session.refresh(seller)
        payload["seller_exception"] = {
            "seller_id": str(seller.id),
            "amount": "3.00",
            "valid_from": (today - timedelta(days=1)).isoformat(),
        }

    response = await async_client.post(
        "/operations/storage/tariffs",
        headers=headers,
        json=payload,
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"] == "tariff_valid_from_in_past"
    async with SessionLocal() as session:
        count = await session.scalar(
            select(func.count(BillingTariffVersion.id)).where(
                BillingTariffVersion.warehouse_id == warehouse_id
            )
        )
    assert count == 0


@pytest.mark.asyncio
async def test_tariff_scope_must_belong_to_tenant_and_operational_warehouse(
    async_client: AsyncClient,
) -> None:
    """Every invalid scope rejects the atomic tariff pair before either row is written."""
    suffix = str(time.time_ns())
    headers = await _register_admin(async_client, f"owner-{suffix}")
    service_warehouse_id = await _create_warehouse(
        async_client, headers, suffix, "service"
    )
    operational_warehouse_id = await _create_warehouse(
        async_client, headers, suffix, "operational"
    )
    foreign_headers = await _register_admin(async_client, f"foreign-{suffix}")
    foreign_warehouse_id = await _create_warehouse(
        async_client, foreign_headers, suffix, "foreign"
    )
    today = datetime.now(MOSCOW).date().isoformat()

    async with SessionLocal() as session:
        service_warehouse = await session.get(Warehouse, service_warehouse_id)
        assert service_warehouse is not None
        service_warehouse.is_operational = False
        tenant_id = service_warehouse.tenant_id

        foreign_warehouse = await session.get(Warehouse, foreign_warehouse_id)
        assert foreign_warehouse is not None

        owner_seller = Seller(tenant_id=tenant_id, name=f"Owner seller {suffix}")
        foreign_seller = Seller(
            tenant_id=foreign_warehouse.tenant_id,
            name=f"Foreign seller {suffix}",
        )
        session.add_all([owner_seller, foreign_seller])
        await session.commit()
        await session.refresh(owner_seller)
        owner_seller_id = owner_seller.id
        foreign_seller_id = foreign_seller.id

    missing_warehouse_id = uuid.uuid4()
    missing_seller_id = uuid.uuid4()
    invalid_scopes = [
        (foreign_warehouse_id, owner_seller_id, 404, "warehouse_not_found"),
        (missing_warehouse_id, owner_seller_id, 404, "warehouse_not_found"),
        (service_warehouse_id, owner_seller_id, 422, "warehouse_not_operational"),
        (operational_warehouse_id, foreign_seller_id, 404, "seller_not_found"),
        (operational_warehouse_id, missing_seller_id, 404, "seller_not_found"),
    ]

    for target_warehouse_id, target_seller_id, status_code, detail in invalid_scopes:
        response = await async_client.post(
            "/operations/storage/tariffs",
            headers=headers,
            json={
                "warehouse_id": str(target_warehouse_id),
                "amount": "5.00",
                "valid_from": today,
                "seller_exception": {
                    "seller_id": str(target_seller_id),
                    "amount": "3.00",
                    "valid_from": today,
                },
            },
        )
        assert response.status_code == status_code, response.text
        assert response.json()["detail"] == detail

        async with SessionLocal() as session:
            count = await session.scalar(
                select(func.count(BillingTariffVersion.id)).where(
                    BillingTariffVersion.tenant_id == tenant_id
                )
            )
        assert count == 0

    valid_response = await async_client.post(
        "/operations/storage/tariffs",
        headers=headers,
        json={
            "warehouse_id": str(operational_warehouse_id),
            "amount": "5.00",
            "valid_from": today,
            "seller_exception": {
                "seller_id": str(owner_seller_id),
                "amount": "3.00",
                "valid_from": today,
            },
        },
    )
    assert valid_response.status_code == 201, valid_response.text

    async with SessionLocal() as session:
        tariffs = list(
            (
                await session.scalars(
                    select(BillingTariffVersion)
                    .where(BillingTariffVersion.tenant_id == tenant_id)
                    .order_by(BillingTariffVersion.seller_id)
                )
            ).all()
        )
    assert len(tariffs) == 2
    assert {tariff.warehouse_id for tariff in tariffs} == {operational_warehouse_id}
    assert {tariff.seller_id for tariff in tariffs} == {None, owner_seller_id}


@pytest.mark.asyncio
async def test_new_tariff_reprices_open_draft_on_reload(async_client: AsyncClient) -> None:
    """Reloading statements after POST shows a preview calculated with the new dated rate."""
    suffix = str(time.time_ns())
    headers = await _register_admin(async_client, suffix)
    warehouse_id = await _create_warehouse(async_client, headers, suffix, "preview")
    today = datetime.now(MOSCOW).date()
    period_start, period_end = month_bounds(today.year, today.month)

    async with SessionLocal() as session:
        warehouse = await session.get(Warehouse, warehouse_id)
        assert warehouse is not None
        seller = Seller(tenant_id=warehouse.tenant_id, name=f"Preview seller {suffix}")
        session.add(seller)
        await session.flush()
        product = Product(
            tenant_id=warehouse.tenant_id,
            seller_id=seller.id,
            name="Preview product",
            sku_code=f"preview-{suffix}",
            volume_liters=Decimal("1"),
            dimensions_source="manual",
        )
        session.add(product)
        await session.flush()
        location = await get_or_create_sorting_location(
            session, warehouse.tenant_id, warehouse.id
        )
        movement = InventoryMovement(
            tenant_id=warehouse.tenant_id,
            seller_id=seller.id,
            warehouse_id=warehouse.id,
            storage_location_id=location.id,
            product_id=product.id,
            quantity_delta=1,
            movement_type="storage_tariff_preview_test",
            created_at=datetime.combine(period_start, datetime_time.min, MOSCOW),
        )
        session.add(movement)
        await session.flush()
        session.add_all(
            [
                StorageStatement(
                    tenant_id=warehouse.tenant_id,
                    seller_id=seller.id,
                    warehouse_id=warehouse.id,
                    period_start=period_start,
                    period_end=period_end,
                    status="draft",
                ),
                StorageMeasurement(
                    tenant_id=warehouse.tenant_id,
                    seller_id=seller.id,
                    warehouse_id=warehouse.id,
                    product_id=product.id,
                    movement_start_id=movement.id,
                    movement_end_id=movement.id,
                    period_start=period_start,
                    period_end=period_end,
                    quantity_days=Decimal("1"),
                    liter_days=Decimal("1"),
                    status="calculated",
                ),
                BillingTariffVersion(
                    tenant_id=warehouse.tenant_id,
                    seller_id=None,
                    warehouse_id=warehouse.id,
                    service_code="storage_liter_day",
                    unit="liter_day",
                    amount=Decimal("1.00"),
                    valid_from=period_start,
                ),
            ]
        )
        await session.commit()

    before = await async_client.get(
        "/operations/storage/statements",
        headers=headers,
        params={"year": today.year, "month": today.month, "warehouse_id": str(warehouse_id)},
    )
    assert before.status_code == 200, before.text
    before_amount = Decimal(before.json()["statements"][0]["total_amount"])

    created = await async_client.post(
        "/operations/storage/tariffs",
        headers=headers,
        json={
            "warehouse_id": str(warehouse_id),
            "amount": "10.00",
            "valid_from": today.isoformat(),
        },
    )
    assert created.status_code == 201, created.text

    after = await async_client.get(
        "/operations/storage/statements",
        headers=headers,
        params={"year": today.year, "month": today.month, "warehouse_id": str(warehouse_id)},
    )
    assert after.status_code == 200, after.text
    after_statement = after.json()["statements"][0]
    assert Decimal(after_statement["total_amount"]) > before_amount
    assert after_statement["measurements"][0]["rate_snapshot"] is not None
