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
from app.models.warehouse import Warehouse
from app.services import storage_statement_service
from app.services.sorting_location_service import get_or_create_sorting_location
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
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    amount: str,
) -> None:
    """The API rejects common and seller rates that persist as zero."""
    reprice_called = False

    async def unexpected_reprice(*args: object, **kwargs: object) -> list[object]:
        nonlocal reprice_called
        reprice_called = True
        return []

    monkeypatch.setattr(
        storage_statement_service,
        "reprice_open_storage_drafts",
        unexpected_reprice,
    )
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
    assert reprice_called is False
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
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    """The service keeps the persisted-money guard for callers outside the API."""
    reprice_called = False

    async def unexpected_reprice(*args: object, **kwargs: object) -> list[object]:
        nonlocal reprice_called
        reprice_called = True
        return []

    monkeypatch.setattr(
        storage_statement_service,
        "reprice_open_storage_drafts",
        unexpected_reprice,
    )
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
    assert reprice_called is False


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
async def test_new_tariff_reprices_open_draft_on_reload(async_client: AsyncClient) -> None:
    """POST reprices affected drafts but preserves fixed and unrelated statements."""
    suffix = str(time.time_ns())
    headers = await _register_admin(async_client, suffix)
    warehouse_id = await _create_warehouse(async_client, headers, suffix, "preview")
    unrelated_warehouse_id = await _create_warehouse(
        async_client, headers, suffix, "unrelated"
    )
    today = datetime.now(MOSCOW).date()
    period_start, period_end = month_bounds(today.year, today.month)
    previous_period_end = period_start - timedelta(days=1)
    previous_period_start = previous_period_end.replace(day=1)

    async with SessionLocal() as session:
        warehouse = await session.get(Warehouse, warehouse_id)
        assert warehouse is not None
        sellers = [
            Seller(tenant_id=warehouse.tenant_id, name=f"Draft seller {suffix}"),
            Seller(tenant_id=warehouse.tenant_id, name=f"Zero seller {suffix}"),
            Seller(tenant_id=warehouse.tenant_id, name=f"Fixed seller {suffix}"),
            Seller(tenant_id=warehouse.tenant_id, name=f"Unrelated seller {suffix}"),
        ]
        session.add_all(sellers)
        await session.flush()
        draft_seller, zero_seller, fixed_seller, unrelated_seller = sellers
        draft_product = Product(
            tenant_id=warehouse.tenant_id,
            seller_id=draft_seller.id,
            name="Draft product",
            sku_code=f"draft-{suffix}",
            volume_liters=Decimal("1"),
            dimensions_source="manual",
        )
        zero_product = Product(
            tenant_id=warehouse.tenant_id,
            seller_id=zero_seller.id,
            name="Zero product",
            sku_code=f"zero-{suffix}",
            volume_liters=Decimal("1"),
            dimensions_source="manual",
        )
        fixed_product = Product(
            tenant_id=warehouse.tenant_id,
            seller_id=fixed_seller.id,
            name="Fixed product",
            sku_code=f"fixed-{suffix}",
            volume_liters=Decimal("1"),
            dimensions_source="manual",
        )
        session.add_all([draft_product, zero_product, fixed_product])
        await session.flush()
        location = await get_or_create_sorting_location(
            session, warehouse.tenant_id, warehouse.id
        )
        draft_movement = InventoryMovement(
            tenant_id=warehouse.tenant_id,
            seller_id=draft_seller.id,
            warehouse_id=warehouse.id,
            storage_location_id=location.id,
            product_id=draft_product.id,
            quantity_delta=1,
            movement_type="storage_tariff_preview_test",
            created_at=datetime.combine(period_start, datetime_time.min, MOSCOW),
        )
        fixed_movement = InventoryMovement(
            tenant_id=warehouse.tenant_id,
            seller_id=fixed_seller.id,
            warehouse_id=warehouse.id,
            storage_location_id=location.id,
            product_id=fixed_product.id,
            quantity_delta=1,
            movement_type="storage_tariff_fixed_control_test",
            created_at=datetime.combine(period_start, datetime_time.min, MOSCOW),
        )
        session.add_all([draft_movement, fixed_movement])
        await session.flush()
        initial_tariff = BillingTariffVersion(
            tenant_id=warehouse.tenant_id,
            seller_id=None,
            warehouse_id=warehouse.id,
            service_code="storage_liter_day",
            unit="liter_day",
            amount=100,
            valid_from=period_start - timedelta(days=1),
        )
        unrelated_tariff = BillingTariffVersion(
            tenant_id=warehouse.tenant_id,
            seller_id=None,
            warehouse_id=unrelated_warehouse_id,
            service_code="storage_liter_day",
            unit="liter_day",
            amount=200,
            valid_from=period_start - timedelta(days=1),
        )
        session.add_all([initial_tariff, unrelated_tariff])
        await session.flush()

        draft_statement = StorageStatement(
            tenant_id=warehouse.tenant_id,
            seller_id=draft_seller.id,
            warehouse_id=warehouse.id,
            period_start=period_start,
            period_end=period_end,
            status="draft",
        )
        zero_statement = StorageStatement(
            tenant_id=warehouse.tenant_id,
            seller_id=zero_seller.id,
            warehouse_id=warehouse.id,
            period_start=period_start,
            period_end=period_end,
            status="draft",
        )
        fixed_statement = StorageStatement(
            tenant_id=warehouse.tenant_id,
            seller_id=fixed_seller.id,
            warehouse_id=warehouse.id,
            period_start=period_start,
            period_end=period_end,
            status="fixed",
            fixed_at=datetime.now(UTC),
        )
        unrelated_statement = StorageStatement(
            tenant_id=warehouse.tenant_id,
            seller_id=unrelated_seller.id,
            warehouse_id=unrelated_warehouse_id,
            period_start=period_start,
            period_end=period_end,
            status="draft",
        )
        past_statement = StorageStatement(
            tenant_id=warehouse.tenant_id,
            seller_id=zero_seller.id,
            warehouse_id=warehouse.id,
            period_start=previous_period_start,
            period_end=previous_period_end,
            status="draft",
        )
        draft_measurement = StorageMeasurement(
            tenant_id=warehouse.tenant_id,
            seller_id=draft_seller.id,
            warehouse_id=warehouse.id,
            product_id=draft_product.id,
            movement_start_id=draft_movement.id,
            movement_end_id=draft_movement.id,
            period_start=period_start,
            period_end=period_end,
            quantity_days=Decimal("1"),
            liter_days=Decimal("1"),
            status="calculated",
        )
        fixed_measurement = StorageMeasurement(
            tenant_id=warehouse.tenant_id,
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
        zero_measurement = StorageMeasurement(
            tenant_id=warehouse.tenant_id,
            seller_id=zero_seller.id,
            warehouse_id=warehouse.id,
            product_id=zero_product.id,
            period_start=period_start,
            period_end=period_end,
            quantity_days=Decimal("0"),
            liter_days=Decimal("0"),
            status="calculated",
        )
        session.add_all(
            [
                draft_statement,
                zero_statement,
                fixed_statement,
                unrelated_statement,
                past_statement,
                draft_measurement,
                fixed_measurement,
                zero_measurement,
            ]
        )
        await session.flush()
        session.add(
            BillingLedgerEntry(
                tenant_id=warehouse.tenant_id,
                seller_id=fixed_seller.id,
                tariff_version_id=initial_tariff.id,
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
        await session.commit()
        tenant_id = warehouse.tenant_id
        draft_statement_id = draft_statement.id
        zero_statement_id = zero_statement.id
        fixed_statement_id = fixed_statement.id
        unrelated_statement_id = unrelated_statement.id
        past_statement_id = past_statement.id
        fixed_measurement_id = fixed_measurement.id

    before = await async_client.get(
        "/operations/storage/statements",
        headers=headers,
        params={"year": today.year, "month": today.month, "warehouse_id": str(warehouse_id)},
    )
    assert before.status_code == 200, before.text
    before_by_id = {item["id"]: item for item in before.json()["statements"]}
    before_amount = Decimal(before_by_id[str(draft_statement_id)]["total_amount"])
    assert before_by_id[str(fixed_statement_id)]["total_amount"] == "1.00"
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
    recalculated = {
        item["id"]: item for item in created.json()["recalculated_statements"]
    }
    assert set(recalculated) == {
        str(draft_statement_id),
        str(zero_statement_id),
        str(unrelated_statement_id),
    }
    assert Decimal(recalculated[str(draft_statement_id)]["total_amount"]) > before_amount
    assert Decimal(recalculated[str(zero_statement_id)]["total_amount"]) == 0
    assert recalculated[str(zero_statement_id)]["measurements"][0]["rate_snapshot"] == "10.00"
    assert str(fixed_statement_id) not in recalculated
    assert str(unrelated_statement_id) in recalculated
    assert str(past_statement_id) not in recalculated

    after = await async_client.get(
        "/operations/storage/statements",
        headers=headers,
        params={"year": today.year, "month": today.month, "warehouse_id": str(warehouse_id)},
    )
    assert after.status_code == 200, after.text
    after_by_id = {item["id"]: item for item in after.json()["statements"]}
    assert Decimal(after_by_id[str(draft_statement_id)]["total_amount"]) >= Decimal(
        recalculated[str(draft_statement_id)]["total_amount"]
    )
    assert after_by_id[str(draft_statement_id)]["measurements"][0]["rate_snapshot"] is not None
    assert after_by_id[str(fixed_statement_id)]["total_amount"] == "1.00"
    assert after_by_id[str(fixed_statement_id)]["measurements"][0]["rate_snapshot"] == "1.00"

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
    after_failed = await async_client.get(
        "/operations/storage/statements",
        headers=headers,
        params={"year": today.year, "month": today.month, "warehouse_id": str(warehouse_id)},
    )
    assert after_failed.status_code == 200, after_failed.text
    after_failed_by_id = {
        item["id"]: item for item in after_failed.json()["statements"]
    }
    assert Decimal(after_failed_by_id[str(draft_statement_id)]["total_amount"]) >= Decimal(
        after_by_id[str(draft_statement_id)]["total_amount"]
    )

    async with SessionLocal() as session:
        ledger_rows = list(
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
                    )
                )
            ).all()
        )
    assert len(ledger_rows) == 1
    assert ledger_rows[0].source_id == fixed_measurement_id
    assert ledger_rows[0].rate == 100
    assert ledger_rows[0].amount == 100
    assert len(new_tariffs) == 1
    assert new_tariffs[0].rate == 1000


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
