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
from datetime import UTC, datetime, timedelta
from datetime import time as datetime_time
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.billing import BillingLedgerEntry, BillingTariffVersion, BillingTariffVersionV2
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.seller import Seller
from app.models.storage_measurement import StorageMeasurement
from app.models.storage_statement import StorageStatement
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services.sorting_location_service import get_or_create_sorting_location
from app.services.storage_daily_charge_service import charge_storage_day
from app.services.storage_measurement_service import MOSCOW, month_bounds
from app.services.storage_statement_service import (
    StorageStatementError,
    create_storage_tariff,
)

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
    """POST common rate → one V2 row and no legacy warehouse tariff."""
    suffix = str(time.time_ns())
    headers = await _register_admin(async_client, suffix)
    warehouse_id = await _create_warehouse(async_client, headers, suffix, "common")
    valid_from = datetime.now(MOSCOW).date()
    matrix = await async_client.get("/billing/tariff-matrix", headers=headers)
    assert matrix.status_code == 200, matrix.text

    resp = await async_client.post(
        "/operations/storage/tariffs",
        headers=headers,
        json={
            "revision": matrix.json()["revision"],
            "amount": "5.00",
            "valid_from": valid_from.isoformat(),
        },
    )
    assert resp.status_code == 201, resp.text

    body = resp.json()
    assert body["warehouse_tariff"]["seller_id"] is None
    assert body["warehouse_tariff"]["warehouse_id"] is None
    assert body["warehouse_tariff"]["amount"] == "5.00"
    assert body["warehouse_tariff"]["valid_from"] == valid_from.isoformat()
    assert body["seller_exception"] is None

    async with SessionLocal() as session:
        count = await session.scalar(
            select(func.count(BillingTariffVersionV2.id)).where(
                BillingTariffVersionV2.tenant_id
                == select(Warehouse.tenant_id)
                .where(Warehouse.id == warehouse_id)
                .scalar_subquery(),
                BillingTariffVersionV2.seller_id.is_(None),
                BillingTariffVersionV2.service_code == "storage",
            )
        )
    assert count == 1
    async with SessionLocal() as session:
        legacy_count = await session.scalar(
            select(func.count(BillingTariffVersion.id)).where(
                BillingTariffVersion.warehouse_id == warehouse_id,
                BillingTariffVersion.service_code == "storage_liter_day",
            )
        )
    assert legacy_count == 0


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
    matrix = await async_client.get("/billing/tariff-matrix", headers=headers)
    assert matrix.status_code == 200, matrix.text

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
            "revision": matrix.json()["revision"],
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
            select(func.count(BillingTariffVersionV2.id)).where(
                BillingTariffVersionV2.tenant_id == tenant_id,
                BillingTariffVersionV2.service_code == "storage",
            )
        )
    assert total == 2

    # --- Atomicity: pre-seed a conflicting V2 seller tariff, then POST again ---
    atomic_warehouse_valid_from = today + timedelta(days=3)
    atomic_seller_valid_from = today + timedelta(days=4)

    async with SessionLocal() as session:
        seller2 = Seller(tenant_id=tenant_id, name=f"AtomSeller {suffix}")
        session.add(seller2)
        await session.flush()
        seller2_id = seller2.id
        # Pre-seed a dated seller tariff that will conflict with the POST below.
        session.add(
            BillingTariffVersionV2(
                tenant_id=tenant_id,
                seller_id=seller2_id,
                product_id=None,
                employee_user_id=None,
                service_code="storage",
                unit="liter_day",
                enabled=True,
                rate=200,
                    valid_from_at=datetime.combine(
                        atomic_seller_valid_from, datetime_time.min, MOSCOW
                    ).astimezone(UTC),
            )
        )
        await session.commit()

    # POST: the warehouse date is free, while the seller exception conflicts.
    conflict_resp = await async_client.post(
        "/operations/storage/tariffs",
        headers=headers,
        json={
            "revision": matrix.json()["revision"] + 1,
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
            select(func.count(BillingTariffVersionV2.id)).where(
                BillingTariffVersionV2.tenant_id == tenant_id,
                BillingTariffVersionV2.seller_id.is_(None),
                BillingTariffVersionV2.service_code == "storage",
                BillingTariffVersionV2.valid_from_at
                == datetime.combine(
                    atomic_warehouse_valid_from, datetime_time.min, MOSCOW
                ).astimezone(UTC),
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
        ("warehouse", "0.001"),
        ("seller_exception", "0"),
        ("seller_exception", "-0.01"),
        ("seller_exception", "0.001"),
    ],
)
async def test_tariff_amount_must_be_positive(
    async_client: AsyncClient,
    target: str,
    amount: str,
) -> None:
    """The API rejects common and seller rates that persist as zero."""
    suffix = str(time.time_ns())
    headers = await _register_admin(async_client, suffix)
    warehouse_id = await _create_warehouse(async_client, headers, suffix, "amount")
    matrix = await async_client.get("/billing/tariff-matrix", headers=headers)
    assert matrix.status_code == 200, matrix.text
    today = datetime.now(MOSCOW).date().isoformat()
    payload: dict[str, object] = {
        "revision": matrix.json()["revision"],
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
        legacy_count = await session.scalar(
            select(func.count(BillingTariffVersion.id)).where(
                BillingTariffVersion.warehouse_id == warehouse_id
            )
        )
        warehouse = await session.get(Warehouse, warehouse_id)
        assert warehouse is not None
        v2_count = await session.scalar(
            select(func.count(BillingTariffVersionV2.id)).where(
                BillingTariffVersionV2.tenant_id == warehouse.tenant_id,
                BillingTariffVersionV2.service_code == "storage",
            )
        )
    assert legacy_count == v2_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["warehouse", "seller_exception"])
async def test_storage_tariff_service_rejects_amount_rounding_to_zero(
    target: str,
) -> None:
    """The service keeps the persisted-money guard for callers outside the API."""
    tenant_id = uuid.uuid4()
    seller_exception = (
        (uuid.uuid4(), Decimal("0.001"), datetime.now(MOSCOW).date())
        if target == "seller_exception"
        else None
    )
    warehouse_amount = Decimal("0.001") if target == "warehouse" else Decimal("5.00")
    session = AsyncMock(spec=AsyncSession)

    with pytest.raises(
        StorageStatementError,
        match=r"^tariff_amount_must_be_positive$",
    ):
        await create_storage_tariff(
            session,
            tenant_id,
            warehouse_amount,
            datetime.now(MOSCOW).date(),
            0,
            seller_exception,
        )

    session.scalar.assert_not_awaited()
    session.add.assert_not_called()
    session.flush.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_tariff_amount_rounding_that_stays_positive_is_saved(
    async_client: AsyncClient,
) -> None:
    """Half a kopeck rounds to one kopeck for both tariff scopes."""
    suffix = str(time.time_ns())
    headers = await _register_admin(async_client, suffix)
    warehouse_id = await _create_warehouse(async_client, headers, suffix, "rounded")
    today = datetime.now(MOSCOW).date()
    matrix = await async_client.get("/billing/tariff-matrix", headers=headers)
    assert matrix.status_code == 200, matrix.text

    async with SessionLocal() as session:
        warehouse = await session.get(Warehouse, warehouse_id)
        assert warehouse is not None
        seller = Seller(tenant_id=warehouse.tenant_id, name=f"Rounded seller {suffix}")
        session.add(seller)
        await session.commit()
        await session.refresh(seller)
        seller_id = seller.id

    response = await async_client.post(
        "/operations/storage/tariffs",
        headers=headers,
        json={
            "revision": matrix.json()["revision"],
            "amount": "0.005",
            "valid_from": today.isoformat(),
            "seller_exception": {
                "seller_id": str(seller_id),
                "amount": "0.005",
                "valid_from": today.isoformat(),
            },
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["warehouse_tariff"]["amount"] == "0.01"
    assert response.json()["seller_exception"]["amount"] == "0.01"
    async with SessionLocal() as session:
        stored_amounts = list(
            (
                await session.scalars(
                    select(BillingTariffVersionV2.rate).where(
                        BillingTariffVersionV2.tenant_id == warehouse.tenant_id,
                        BillingTariffVersionV2.service_code == "storage",
                    )
                )
            ).all()
        )
    assert stored_amounts == [1, 1]
    async with SessionLocal() as session:
        legacy_count = await session.scalar(
            select(func.count(BillingTariffVersion.id)).where(
                BillingTariffVersion.warehouse_id == warehouse_id
            )
        )
    assert legacy_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["warehouse", "seller_exception"])
async def test_tariff_valid_from_cannot_be_in_the_past(
    async_client: AsyncClient, target: str
) -> None:
    """Neither common nor seller storage rates can start before Moscow today."""
    suffix = str(time.time_ns())
    headers = await _register_admin(async_client, suffix)
    warehouse_id = await _create_warehouse(async_client, headers, suffix, "past")
    matrix = await async_client.get("/billing/tariff-matrix", headers=headers)
    assert matrix.status_code == 200, matrix.text
    today = datetime.now(MOSCOW).date()
    payload: dict[str, object] = {
        "revision": matrix.json()["revision"],
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
        legacy_count = await session.scalar(
            select(func.count(BillingTariffVersion.id)).where(
                BillingTariffVersion.warehouse_id == warehouse_id
            )
        )
        warehouse = await session.get(Warehouse, warehouse_id)
        assert warehouse is not None
        v2_count = await session.scalar(
            select(func.count(BillingTariffVersionV2.id)).where(
                BillingTariffVersionV2.tenant_id == warehouse.tenant_id,
                BillingTariffVersionV2.service_code == "storage",
            )
        )
    assert legacy_count == v2_count == 0


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
    _operational_warehouse_id = await _create_warehouse(
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

    missing_seller_id = uuid.uuid4()
    matrix = await async_client.get("/billing/tariff-matrix", headers=headers)
    assert matrix.status_code == 200, matrix.text

    for target_seller_id in (foreign_seller_id, missing_seller_id):
        response = await async_client.post(
            "/operations/storage/tariffs",
            headers=headers,
            json={
                "revision": matrix.json()["revision"],
                "amount": "5.00",
                "valid_from": today,
                "seller_exception": {
                    "seller_id": str(target_seller_id),
                    "amount": "3.00",
                    "valid_from": today,
                },
            },
        )
        assert response.status_code == 404, response.text

        async with SessionLocal() as session:
            count = await session.scalar(
                select(func.count(BillingTariffVersionV2.id)).where(
                    BillingTariffVersionV2.tenant_id == tenant_id,
                    BillingTariffVersionV2.service_code == "storage",
                )
            )
        assert count == 0

    valid_response = await async_client.post(
        "/operations/storage/tariffs",
        headers=headers,
        json={
            "revision": matrix.json()["revision"],
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
                    select(BillingTariffVersionV2)
                    .where(BillingTariffVersionV2.tenant_id == tenant_id)
                    .order_by(BillingTariffVersionV2.seller_id)
                )
            ).all()
        )
    assert len(tariffs) == 2
    assert {tariff.seller_id for tariff in tariffs} == {None, owner_seller_id}


@pytest.mark.asyncio
async def test_new_tariff_does_not_rewrite_what_the_night_already_charged(
    async_client: AsyncClient,
) -> None:
    """Новая ставка меняет будущее, а не прошлое.

    Пересчёт открытых расчётов по свежей ставке снят намеренно: хранение
    начисляет ночь по ставке, действовавшей в те сутки, и это факт, а не
    черновик. Здесь проверяется и то, и другое: начисленное остаётся как было, а
    документ, зафиксированный до перехода на ночное начисление, продолжает
    печататься своими проводками.
    """
    suffix = str(time.time_ns())
    headers = await _register_admin(async_client, suffix)
    warehouse_id = await _create_warehouse(async_client, headers, suffix, "preview")
    today = datetime.now(MOSCOW).date()
    period_start, period_end = month_bounds(today.year, today.month)
    charged_day = today - timedelta(days=1) if today.day > 1 else today

    async with SessionLocal() as session:
        warehouse = await session.get(Warehouse, warehouse_id)
        assert warehouse is not None
        tenant_id = warehouse.tenant_id
        tenant = await session.get(Tenant, tenant_id)
        assert tenant is not None
        tenant.billing_enabled_from = period_start
        night_seller = Seller(tenant_id=tenant_id, name=f"Night seller {suffix}")
        fixed_seller = Seller(tenant_id=tenant_id, name=f"Fixed seller {suffix}")
        session.add_all([night_seller, fixed_seller])
        await session.flush()
        night_product = Product(
            tenant_id=tenant_id,
            seller_id=night_seller.id,
            name="Night product",
            sku_code=f"night-{suffix}",
            volume_liters=Decimal("1"),
            dimensions_source="manual",
        )
        fixed_product = Product(
            tenant_id=tenant_id,
            seller_id=fixed_seller.id,
            name="Fixed product",
            sku_code=f"fixed-{suffix}",
            volume_liters=Decimal("1"),
            dimensions_source="manual",
        )
        session.add_all([night_product, fixed_product])
        await session.flush()
        location = await get_or_create_sorting_location(session, tenant_id, warehouse.id)
        night_movement = InventoryMovement(
            tenant_id=tenant_id,
            seller_id=night_seller.id,
            warehouse_id=warehouse.id,
            storage_location_id=location.id,
            product_id=night_product.id,
            quantity_delta=1,
            movement_type="storage_tariff_night_test",
            created_at=datetime.combine(period_start, datetime_time.min, MOSCOW),
        )
        fixed_movement = InventoryMovement(
            tenant_id=tenant_id,
            seller_id=fixed_seller.id,
            warehouse_id=warehouse.id,
            storage_location_id=location.id,
            product_id=fixed_product.id,
            quantity_delta=1,
            movement_type="storage_tariff_fixed_control_test",
            created_at=datetime.combine(period_start, datetime_time.min, MOSCOW),
        )
        night_statement = StorageStatement(
            tenant_id=tenant_id,
            seller_id=night_seller.id,
            warehouse_id=warehouse.id,
            period_start=period_start,
            period_end=period_end,
            status="draft",
        )
        fixed_statement = StorageStatement(
            tenant_id=tenant_id,
            seller_id=fixed_seller.id,
            warehouse_id=warehouse.id,
            period_start=period_start,
            period_end=period_end,
            status="fixed",
            fixed_at=datetime.now(UTC),
        )
        session.add_all(
            [
                night_movement,
                fixed_movement,
                night_statement,
                fixed_statement,
                BillingTariffVersionV2(
                    tenant_id=tenant_id,
                    seller_id=None,
                    product_id=None,
                    employee_user_id=None,
                    service_code="storage",
                    unit="liter_day",
                    enabled=True,
                    rate=200,
                    valid_from_at=datetime.combine(period_start, datetime_time.min, MOSCOW),
                ),
            ]
        )
        await session.flush()
        night_measurement = StorageMeasurement(
            tenant_id=tenant_id,
            seller_id=night_seller.id,
            warehouse_id=warehouse.id,
            product_id=night_product.id,
            movement_start_id=night_movement.id,
            movement_end_id=night_movement.id,
            period_start=period_start,
            period_end=period_end,
            quantity_days=Decimal("1"),
            liter_days=Decimal("1"),
            status="calculated",
        )
        fixed_measurement = StorageMeasurement(
            tenant_id=tenant_id,
            seller_id=fixed_seller.id,
            warehouse_id=warehouse.id,
            product_id=fixed_product.id,
            movement_start_id=fixed_movement.id,
            movement_end_id=fixed_movement.id,
            period_start=period_start,
            period_end=period_end,
            quantity_days=Decimal("1"),
            liter_days=Decimal("1"),
            status="calculated",
        )
        session.add_all([night_measurement, fixed_measurement])
        await session.flush()
        session.add(
            BillingLedgerEntry(
                tenant_id=tenant_id,
                seller_id=fixed_seller.id,
                service_code="storage_liter_day",
                source="storage_statement",
                source_type="storage_measurement",
                source_id=fixed_measurement.id,
                unit="liter_day",
                quantity=Decimal("1"),
                rate=100,
                amount=100,
                occurred_at=datetime.now(UTC),
            )
        )
        night_statement_id = night_statement.id
        fixed_statement_id = fixed_statement.id
        await session.commit()

    async with SessionLocal() as session:
        assert await charge_storage_day(session, tenant_id, day=charged_day) == 2

    async def listed() -> dict[str, dict[str, object]]:
        response = await async_client.get(
            "/operations/storage/statements",
            headers=headers,
            params={"year": today.year, "month": today.month, "warehouse_id": str(warehouse_id)},
        )
        assert response.status_code == 200, response.text
        return {item["id"]: item for item in response.json()["statements"]}

    before = await listed()
    assert before[str(night_statement_id)]["total_amount"] == "2.00"
    assert before[str(fixed_statement_id)]["total_amount"] == "1.00"

    matrix = await async_client.get("/billing/tariff-matrix", headers=headers)
    assert matrix.status_code == 200, matrix.text
    created = await async_client.post(
        "/operations/storage/tariffs",
        headers=headers,
        json={
            "revision": matrix.json()["revision"],
            "amount": "10.00",
            "valid_from": today.isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    # Ответа «пересчитанные ведомости» больше нет: пересчитывать нечего.
    assert "recalculated_statements" not in created.json()

    after = await listed()
    assert after[str(night_statement_id)]["total_amount"] == "2.00"
    assert after[str(night_statement_id)]["measurements"][0]["rate_snapshot"] == "2.00"
    assert after[str(fixed_statement_id)]["total_amount"] == "1.00"
    assert after[str(fixed_statement_id)]["measurements"][0]["rate_snapshot"] == "1.00"

    failed = await async_client.post(
        "/operations/storage/tariffs",
        headers=headers,
        json={
            "revision": created.json()["tariff_revision"],
            "amount": "20.00",
            "valid_from": today.isoformat(),
        },
    )
    assert failed.status_code == 409, failed.text
    after_failed = await listed()
    assert after_failed[str(night_statement_id)]["total_amount"] == "2.00"

    async with SessionLocal() as session:
        legacy_rows = list(
            (
                await session.scalars(
                    select(BillingLedgerEntry).where(
                        BillingLedgerEntry.tenant_id == tenant_id,
                        BillingLedgerEntry.service_code == "storage_liter_day",
                    )
                )
            ).all()
        )
        new_tariffs = list(
            (
                await session.scalars(
                    select(BillingTariffVersionV2).where(
                        BillingTariffVersionV2.tenant_id == tenant_id,
                        BillingTariffVersionV2.service_code == "storage",
                        BillingTariffVersionV2.rate == 1000,
                    )
                )
            ).all()
        )
    assert len(legacy_rows) == 1
    assert legacy_rows[0].rate == 100
    assert legacy_rows[0].amount == 100
    assert len(new_tariffs) == 1


@pytest.mark.asyncio
async def test_tariff_rejects_rubles_above_postgres_kopeck_limit_without_write(
    async_client: AsyncClient,
) -> None:
    suffix = str(time.time_ns())
    headers = await _register_admin(async_client, suffix)
    warehouse_id = await _create_warehouse(async_client, headers, suffix, "overflow")
    matrix = await async_client.get("/billing/tariff-matrix", headers=headers)
    assert matrix.status_code == 200, matrix.text

    response = await async_client.post(
        "/operations/storage/tariffs",
        headers=headers,
        json={
            "revision": matrix.json()["revision"],
            "amount": "21474836.48",
            "valid_from": datetime.now(MOSCOW).date().isoformat(),
        },
    )

    assert response.status_code == 422, response.text
    async with SessionLocal() as session:
        legacy_count = await session.scalar(
            select(func.count(BillingTariffVersion.id)).where(
                BillingTariffVersion.warehouse_id == warehouse_id,
                BillingTariffVersion.service_code == "storage_liter_day",
            )
        )
        warehouse = await session.get(Warehouse, warehouse_id)
        assert warehouse is not None
        v2_count = await session.scalar(
            select(func.count(BillingTariffVersionV2.id)).where(
                BillingTariffVersionV2.tenant_id == warehouse.tenant_id,
                BillingTariffVersionV2.service_code == "storage",
            )
        )
    assert legacy_count == v2_count == 0
