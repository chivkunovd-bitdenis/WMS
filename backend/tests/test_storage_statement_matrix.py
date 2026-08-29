"""A-1 contract tests for the V2 storage-statement tariff path."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, date, datetime, timedelta
from datetime import time as datetime_time
from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.billing import (
    BillingLedgerEntry,
    BillingTariffVersion,
    BillingTariffVersionV2,
)
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.product_dimension_event import ProductDimensionEvent
from app.models.seller import Seller
from app.models.storage_measurement import StorageMeasurement
from app.models.storage_statement import StorageStatement
from app.models.warehouse import Warehouse
from app.services import storage_statement_service
from app.services.sorting_location_service import get_or_create_sorting_location
from app.services.storage_measurement_service import MOSCOW


async def _admin(async_client: AsyncClient, suffix: str) -> tuple[dict[str, str], int]:
    registered = await async_client.post(
        "/auth/register",
        json={
            "organization_name": f"Storage matrix {suffix}",
            "slug": f"storage-matrix-{suffix}",
            "admin_email": f"storage-matrix-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registered.status_code == 200, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    matrix = await async_client.get("/billing/tariff-matrix", headers=headers)
    assert matrix.status_code == 200, matrix.text
    return headers, matrix.json()["revision"]


async def _seller(async_client: AsyncClient, headers: dict[str, str], name: str) -> uuid.UUID:
    response = await async_client.post("/sellers", headers=headers, json={"name": name})
    assert response.status_code == 201, response.text
    return uuid.UUID(response.json()["id"])


@pytest.mark.asyncio
async def test_storage_facade_writes_only_common_and_seller_v2_rates(
    async_client: AsyncClient,
) -> None:
    """TC-NEW-A1-005: legacy warehouse rates are never created by the facade."""
    suffix = str(time.time_ns())
    headers, revision = await _admin(async_client, suffix)
    seller_id = await _seller(async_client, headers, f"Seller {suffix}")
    today = datetime.now(MOSCOW).date()
    created = await async_client.post(
        "/operations/storage/tariffs",
        headers=headers,
        json={
            "revision": revision,
            "amount": "5.00",
            "valid_from": today.isoformat(),
            "seller_exception": {
                "seller_id": str(seller_id),
                "amount": "3.00",
                "valid_from": today.isoformat(),
            },
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["warehouse_tariff"]["warehouse_id"] is None
    async with SessionLocal() as session:
        tenant_id = await session.scalar(select(Seller.tenant_id).where(Seller.id == seller_id))
        assert tenant_id is not None
        legacy_count = await session.scalar(
            select(func.count(BillingTariffVersion.id)).where(
                BillingTariffVersion.tenant_id == tenant_id,
                BillingTariffVersion.service_code == "storage_liter_day",
            )
        )
        rows = list(
            (
                await session.scalars(
                    select(BillingTariffVersionV2).where(
                        BillingTariffVersionV2.tenant_id == tenant_id,
                        BillingTariffVersionV2.service_code == "storage",
                    )
                )
            ).all()
        )
    assert legacy_count == 0
    assert {(row.seller_id, row.rate) for row in rows} == {(None, 500), (seller_id, 300)}


@pytest.mark.asyncio
async def test_stale_storage_submit_rolls_back_the_common_seller_pair(
    async_client: AsyncClient,
) -> None:
    """TC-NEW-A1-005 negative: stale revision leaves no partial V2 pair."""
    suffix = str(time.time_ns())
    headers, revision = await _admin(async_client, suffix)
    seller_id = await _seller(async_client, headers, f"Seller {suffix}")
    today = datetime.now(MOSCOW).date()
    first = await async_client.post(
        "/operations/storage/tariffs",
        headers=headers,
        json={"revision": revision, "amount": "2.00", "valid_from": today.isoformat()},
    )
    assert first.status_code == 201, first.text
    stale = await async_client.post(
        "/operations/storage/tariffs",
        headers=headers,
        json={
            "revision": revision,
            "amount": "5.00",
            "valid_from": (today + timedelta(days=1)).isoformat(),
            "seller_exception": {
                "seller_id": str(seller_id),
                "amount": "3.00",
                "valid_from": (today + timedelta(days=1)).isoformat(),
            },
        },
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["detail"] == "billing_tariff_matrix_stale_revision"
    async with SessionLocal() as session:
        seller_rows = list(
            (
                await session.scalars(
                    select(BillingTariffVersionV2).where(
                        BillingTariffVersionV2.service_code == "storage",
                        BillingTariffVersionV2.seller_id == seller_id,
                    )
                )
            ).all()
        )
    assert seller_rows == []


@pytest.mark.asyncio
async def test_common_storage_rate_covers_every_operational_warehouse(
    async_client: AsyncClient,
) -> None:
    """TC-NEW-A1-005: a rate does not inherit the page warehouse filter."""
    suffix = str(time.time_ns())
    headers, revision = await _admin(async_client, suffix)
    for code in ("first", "second"):
        response = await async_client.post(
            "/warehouses", headers=headers, json={"name": code, "code": f"{code}-{suffix}"}
        )
        assert response.status_code == 200, response.text
    today = datetime.now(MOSCOW).date()
    created = await async_client.post(
        "/operations/storage/tariffs",
        headers=headers,
        json={"revision": revision, "amount": "2.00", "valid_from": today.isoformat()},
    )
    assert created.status_code == 201, created.text
    listed = await async_client.get(
        "/operations/storage/statements",
        headers=headers,
        params={"year": today.year, "month": today.month},
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["tariff_configured"] is True


@pytest.mark.asyncio
async def test_statement_report_and_invoice_use_seller_matrix_rate_not_legacy_warehouse_rate(
    async_client: AsyncClient,
) -> None:
    """TC-NEW-A1-001/002: 99 legacy, 2 common and 3 seller remain one price.

    Two warehouse statements intentionally make an accidental page-warehouse
    scope visible.  The invoice consumes the signed seller-report calculation
    token, so this checks the actual route by which the operator makes the
    invoice rather than comparing two private helper calls.
    """
    suffix = str(time.time_ns())
    headers, _revision = await _admin(async_client, suffix)
    seller_id = await _seller(async_client, headers, f"Seller {suffix}")
    warehouse_ids: list[uuid.UUID] = []
    for number in (1, 2):
        warehouse = await async_client.post(
            "/warehouses",
            headers=headers,
            json={"name": f"Warehouse {number}", "code": f"matrix-{number}-{suffix}"},
        )
        assert warehouse.status_code == 200, warehouse.text
        warehouse_ids.append(uuid.UUID(warehouse.json()["id"]))

    period_start = date(2026, 7, 1)
    period_end = date(2026, 7, 31)
    statement_ids: list[uuid.UUID] = []
    async with SessionLocal() as session:
        first_warehouse = await session.get(Warehouse, warehouse_ids[0])
        assert first_warehouse is not None
        tenant_id = first_warehouse.tenant_id
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name="Matrix priced product",
            sku_code=f"matrix-sku-{suffix}",
            volume_liters=1,
            dimensions_source="manual",
        )
        session.add(product)
        await session.flush()
        dimension = ProductDimensionEvent(
            tenant_id=tenant_id,
            product_id=product.id,
            source="manual",
            observed_at=datetime.combine(period_start, datetime_time.min, MOSCOW),
            volume_liters=Decimal("1"),
            applied=True,
            fingerprint=f"matrix-dimension-{suffix}",
        )
        session.add(dimension)
        for warehouse_id in warehouse_ids:
            location = await get_or_create_sorting_location(session, tenant_id, warehouse_id)
            movement = InventoryMovement(
                tenant_id=tenant_id,
                seller_id=seller_id,
                warehouse_id=warehouse_id,
                storage_location_id=location.id,
                product_id=product.id,
                quantity_delta=1,
                movement_type="storage_matrix_contract_test",
                created_at=datetime.combine(period_start, datetime_time.min, MOSCOW),
            )
            statement = StorageStatement(
                tenant_id=tenant_id,
                seller_id=seller_id,
                warehouse_id=warehouse_id,
                period_start=period_start,
                period_end=period_end,
                status="draft",
            )
            session.add_all(
                [
                    movement,
                    statement,
                    # Old warehouse pricing must remain an inert historical row.
                    BillingTariffVersion(
                        tenant_id=tenant_id,
                        seller_id=None,
                        warehouse_id=warehouse_id,
                        service_code="storage_liter_day",
                        unit="liter_day",
                        amount=9900,
                        valid_from=period_start,
                    ),
                ]
            )
            await session.flush()
            session.add(
                StorageMeasurement(
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    warehouse_id=warehouse_id,
                    product_id=product.id,
                    dimension_event_id=dimension.id,
                    movement_start_id=movement.id,
                    movement_end_id=movement.id,
                    period_start=period_start,
                    period_end=period_end,
                    quantity_days=Decimal("31"),
                    liter_days=Decimal("31"),
                    status="calculated",
                )
            )
            statement_ids.append(statement.id)
        session.add_all(
            [
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
                BillingTariffVersionV2(
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    product_id=None,
                    employee_user_id=None,
                    service_code="storage",
                    unit="liter_day",
                    enabled=True,
                    rate=300,
                    valid_from_at=datetime.combine(period_start, datetime_time.min, MOSCOW),
                ),
            ]
        )
        await session.commit()

    statements_response = await async_client.get(
        "/operations/storage/statements",
        headers=headers,
        params={"year": 2026, "month": 7},
    )
    assert statements_response.status_code == 200, statements_response.text
    statements = [
        row
        for row in statements_response.json()["statements"]
        if row["id"] in {str(statement_id) for statement_id in statement_ids}
    ]
    assert len(statements) == 2
    assert {row["total_amount"] for row in statements} == {"93.00"}
    assert {
        measurement["rate_snapshot"] for row in statements for measurement in row["measurements"]
    } == {"3.00"}

    async with SessionLocal() as session:
        repriced = await storage_statement_service.reprice_open_storage_drafts(
            session,
            tenant_id,
            period_start,
        )
    assert {row.statement.id for row in repriced} == set(statement_ids)
    assert {
        tariff.rate for row in repriced for _quantity, _amount, tariff in row.pricing.values()
    } == {300}

    details = await async_client.get(
        f"/billing/seller-report/sellers/{seller_id}/details",
        headers=headers,
        params={
            "date_from": period_start.isoformat(),
            "date_to": period_end.isoformat(),
            "include_finance": "true",
        },
    )
    assert details.status_code == 200, details.text
    storage_row = details.json()["storage_row"]
    assert storage_row["amount_kopecks"] == 18_600
    assert sum(Decimal(row["total_amount"]) for row in statements) == Decimal("186.00")

    invoice = await async_client.post(
        "/billing/invoices-v2/preview",
        headers=headers,
        json={
            "creation_mode": "selected_operations",
            "seller_id": str(seller_id),
            "date_from": period_start.isoformat(),
            "date_to": period_end.isoformat(),
            "selected_root_ids": [],
            "storage_calculation_token": storage_row["calculation_token"],
        },
    )
    assert invoice.status_code == 200, invoice.text
    assert invoice.json()["total_amount_kopecks"] == storage_row["amount_kopecks"]
    assert len(invoice.json()["lines"]) == 1
    assert invoice.json()["lines"][0]["description"] == "Хранение товара за выбранный период"
    assert invoice.json()["lines"][0]["total_amount_kopecks"] == 18_600

    for statement_id in statement_ids:
        fixed = await async_client.post(
            f"/operations/storage/statements/{statement_id}/fix",
            headers=headers,
        )
        assert fixed.status_code == 200, fixed.text

    async with SessionLocal() as session:
        prior_seller_rate = await session.scalar(
            select(BillingTariffVersionV2).where(
                BillingTariffVersionV2.tenant_id == tenant_id,
                BillingTariffVersionV2.seller_id == seller_id,
                BillingTariffVersionV2.service_code == "storage",
            )
        )
        assert prior_seller_rate is not None
        prior_seller_rate.valid_to_at = datetime(2026, 7, 16, tzinfo=MOSCOW)
        session.add(
            BillingTariffVersionV2(
                tenant_id=tenant_id,
                seller_id=seller_id,
                product_id=None,
                employee_user_id=None,
                service_code="storage",
                unit="liter_day",
                enabled=True,
                rate=500,
                valid_from_at=datetime(2026, 7, 16, tzinfo=MOSCOW),
            )
        )
        await session.commit()

    fixed_list = await async_client.get(
        "/operations/storage/statements",
        headers=headers,
        params={"year": 2026, "month": 7},
    )
    assert fixed_list.status_code == 200, fixed_list.text
    fixed_statements = [
        row
        for row in fixed_list.json()["statements"]
        if row["id"] in {str(statement_id) for statement_id in statement_ids}
    ]
    assert {row["status"] for row in fixed_statements} == {"fixed"}
    assert {row["total_amount"] for row in fixed_statements} == {"93.00"}
    assert {
        measurement["rate_snapshot"]
        for row in fixed_statements
        for measurement in row["measurements"]
    } == {"3.00"}


def test_sqlite_naive_utc_tariff_boundary_starts_at_moscow_midnight() -> None:
    """TC-NEW-A1-006: SQLite's naive stored UTC instant is not shifted a day."""
    seller_id = uuid.uuid4()
    common = cast(
        BillingTariffVersionV2,
        SimpleNamespace(
            seller_id=None,
            valid_from_at=datetime(2026, 6, 30, 21, 0),
            valid_to_at=None,
            rate=200,
        ),
    )
    seller = cast(
        BillingTariffVersionV2,
        SimpleNamespace(
            seller_id=seller_id,
            valid_from_at=datetime(2026, 6, 30, 21, 0),
            valid_to_at=None,
            rate=300,
        ),
    )

    assert storage_statement_service._tariff_for_day([common, seller], date(2026, 7, 1)) is seller
    assert storage_statement_service._tariff_for_day([common, seller], date(2026, 6, 30)) is None


@pytest.mark.asyncio
async def test_fractional_measurements_keep_statement_report_and_invoice_at_one_kopeck(
    async_client: AsyncClient,
) -> None:
    """A1-CR-001: allocation may be fractional, but its public total must not lose a kopeck."""
    suffix = str(time.time_ns())
    headers, _revision = await _admin(async_client, suffix)
    seller_id = await _seller(async_client, headers, f"Fractional seller {suffix}")
    created_warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "Fractional", "code": f"fractional-{suffix}"},
    )
    assert created_warehouse.status_code == 200, created_warehouse.text
    warehouse_id = uuid.UUID(created_warehouse.json()["id"])
    period_start = date(2026, 7, 1)
    period_end = date(2026, 7, 31)

    async with SessionLocal() as session:
        warehouse = await session.get(Warehouse, warehouse_id)
        assert warehouse is not None
        tenant_id = warehouse.tenant_id
        statement = StorageStatement(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            period_start=period_start,
            period_end=period_end,
            status="draft",
        )
        session.add_all(
            [
                statement,
                BillingTariffVersionV2(
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    product_id=None,
                    employee_user_id=None,
                    service_code="storage",
                    unit="liter_day",
                    enabled=True,
                    rate=100,
                    valid_from_at=datetime.combine(period_start, datetime_time.min, MOSCOW),
                ),
            ]
        )
        for number in (1, 2):
            product = Product(
                tenant_id=tenant_id,
                seller_id=seller_id,
                name=f"Fractional product {number}",
                sku_code=f"fractional-{number}-{suffix}",
                volume_liters=0.0049,
                dimensions_source="manual",
            )
            session.add(product)
            await session.flush()
            event = ProductDimensionEvent(
                tenant_id=tenant_id,
                product_id=product.id,
                source="manual",
                observed_at=datetime.combine(period_start, datetime_time.min, MOSCOW),
                volume_liters=Decimal("0.0049"),
                applied=True,
                fingerprint=f"fractional-event-{number}-{suffix}",
            )
            location = await get_or_create_sorting_location(session, tenant_id, warehouse_id)
            start = InventoryMovement(
                tenant_id=tenant_id,
                seller_id=seller_id,
                warehouse_id=warehouse_id,
                storage_location_id=location.id,
                product_id=product.id,
                quantity_delta=1,
                movement_type="fractional_storage_test",
                created_at=datetime.combine(period_start, datetime_time.min, MOSCOW),
            )
            end = InventoryMovement(
                tenant_id=tenant_id,
                seller_id=seller_id,
                warehouse_id=warehouse_id,
                storage_location_id=location.id,
                product_id=product.id,
                quantity_delta=-1,
                movement_type="fractional_storage_test",
                created_at=datetime.combine(
                    period_start + timedelta(days=1), datetime_time.min, MOSCOW
                ),
            )
            session.add_all([event, start, end])
            await session.flush()
            session.add(
                StorageMeasurement(
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    warehouse_id=warehouse_id,
                    product_id=product.id,
                    dimension_event_id=event.id,
                    movement_start_id=start.id,
                    movement_end_id=end.id,
                    period_start=period_start,
                    period_end=period_end,
                    quantity_days=Decimal("1"),
                    liter_days=Decimal("0.0049"),
                    status="calculated",
                )
            )
        await session.commit()

    statements = await async_client.get(
        "/operations/storage/statements",
        headers=headers,
        params={"year": 2026, "month": 7},
    )
    assert statements.status_code == 200, statements.text
    statement = next(row for row in statements.json()["statements"] if row["id"])
    statement_kopecks = int((Decimal(statement["total_amount"]) * 100).quantize(Decimal("1")))
    row_kopecks = sum(
        int((Decimal(row["amount"] or "0") * 100).quantize(Decimal("1")))
        for row in statement["measurements"]
    )

    details = await async_client.get(
        f"/billing/seller-report/sellers/{seller_id}/details",
        headers=headers,
        params={
            "date_from": period_start.isoformat(),
            "date_to": period_end.isoformat(),
            "include_finance": "true",
        },
    )
    assert details.status_code == 200, details.text
    report = details.json()["storage_row"]
    invoice = await async_client.post(
        "/billing/invoices-v2/preview",
        headers=headers,
        json={
            "creation_mode": "selected_operations",
            "seller_id": str(seller_id),
            "date_from": period_start.isoformat(),
            "date_to": period_end.isoformat(),
            "selected_root_ids": [],
            "storage_calculation_token": report["calculation_token"],
        },
    )
    assert invoice.status_code == 200, invoice.text
    assert report["liter_days"] == pytest.approx(0.0098)
    assert report["amount_kopecks"] == invoice.json()["total_amount_kopecks"] == 1
    # Rows are publicly visible, so their allocation has to reconcile with the statement total.
    assert row_kopecks == statement_kopecks
    assert statement_kopecks == report["amount_kopecks"] == invoice.json()["total_amount_kopecks"]


async def _create_cross_warehouse_fractional_storage_case(
    async_client: AsyncClient,
) -> tuple[dict[str, str], uuid.UUID, list[uuid.UUID], list[uuid.UUID]]:
    """Create two operational warehouse drafts totaling 0.0098 liter-days."""
    suffix = str(time.time_ns())
    headers, _revision = await _admin(async_client, suffix)
    seller_id = await _seller(async_client, headers, f"Cross-warehouse fractional {suffix}")
    warehouse_ids: list[uuid.UUID] = []
    for number in (1, 2):
        warehouse = await async_client.post(
            "/warehouses",
            headers=headers,
            json={"name": f"Fractional {number}", "code": f"fractional-{number}-{suffix}"},
        )
        assert warehouse.status_code == 200, warehouse.text
        warehouse_ids.append(uuid.UUID(warehouse.json()["id"]))
    period_start = date(2026, 7, 1)
    period_end = date(2026, 7, 31)
    statement_ids: list[uuid.UUID] = []

    async with SessionLocal() as session:
        first_warehouse = await session.get(Warehouse, warehouse_ids[0])
        assert first_warehouse is not None
        tenant_id = first_warehouse.tenant_id
        session.add(
            BillingTariffVersionV2(
                tenant_id=tenant_id,
                seller_id=seller_id,
                product_id=None,
                employee_user_id=None,
                service_code="storage",
                unit="liter_day",
                enabled=True,
                rate=100,
                valid_from_at=datetime.combine(period_start, datetime_time.min, MOSCOW).astimezone(
                    UTC
                ),
            )
        )
        for number, warehouse_id in enumerate(warehouse_ids, start=1):
            product = Product(
                tenant_id=tenant_id,
                seller_id=seller_id,
                name=f"Cross-warehouse fractional product {number}",
                sku_code=f"cross-warehouse-fractional-{number}-{suffix}",
                volume_liters=0.0049,
                dimensions_source="manual",
            )
            session.add(product)
            await session.flush()
            dimension = ProductDimensionEvent(
                tenant_id=tenant_id,
                product_id=product.id,
                source="manual",
                observed_at=datetime.combine(period_start, datetime_time.min, MOSCOW),
                volume_liters=Decimal("0.0049"),
                applied=True,
                fingerprint=f"cross-warehouse-fractional-event-{number}-{suffix}",
            )
            location = await get_or_create_sorting_location(session, tenant_id, warehouse_id)
            movement_in = InventoryMovement(
                tenant_id=tenant_id,
                seller_id=seller_id,
                warehouse_id=warehouse_id,
                storage_location_id=location.id,
                product_id=product.id,
                quantity_delta=1,
                movement_type="cross_warehouse_fractional_storage_test",
                created_at=datetime.combine(period_start, datetime_time.min, MOSCOW),
            )
            movement_out = InventoryMovement(
                tenant_id=tenant_id,
                seller_id=seller_id,
                warehouse_id=warehouse_id,
                storage_location_id=location.id,
                product_id=product.id,
                quantity_delta=-1,
                movement_type="cross_warehouse_fractional_storage_test",
                created_at=datetime.combine(
                    period_start + timedelta(days=1), datetime_time.min, MOSCOW
                ),
            )
            statement = StorageStatement(
                tenant_id=tenant_id,
                seller_id=seller_id,
                warehouse_id=warehouse_id,
                period_start=period_start,
                period_end=period_end,
                status="draft",
            )
            session.add_all([dimension, movement_in, movement_out, statement])
            await session.flush()
            session.add(
                StorageMeasurement(
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    warehouse_id=warehouse_id,
                    product_id=product.id,
                    dimension_event_id=dimension.id,
                    movement_start_id=movement_in.id,
                    movement_end_id=movement_out.id,
                    period_start=period_start,
                    period_end=period_end,
                    quantity_days=Decimal("1"),
                    liter_days=Decimal("0.0049"),
                    status="calculated",
                )
            )
            statement_ids.append(statement.id)
        await session.commit()

    return headers, seller_id, warehouse_ids, statement_ids


@pytest.mark.asyncio
async def test_fractional_warehouse_statements_sum_to_seller_report_and_invoice(
    async_client: AsyncClient,
) -> None:
    """A1-CR-003: allocation cannot lose a seller-day kopeck at warehouse boundaries."""
    headers, seller_id, _warehouse_ids, statement_ids = (
        await _create_cross_warehouse_fractional_storage_case(async_client)
    )
    period_start = date(2026, 7, 1)
    period_end = date(2026, 7, 31)
    statement_response = await async_client.get(
        "/operations/storage/statements",
        headers=headers,
        params={"year": 2026, "month": 7},
    )
    assert statement_response.status_code == 200, statement_response.text
    statements = [
        row
        for row in statement_response.json()["statements"]
        if row["id"] in {str(statement_id) for statement_id in statement_ids}
    ]
    assert len(statements) == 2
    statement_kopecks = sum(
        int((Decimal(row["total_amount"]) * 100).quantize(Decimal("1"))) for row in statements
    )
    allocated_kopecks = sum(
        int((Decimal(measurement["amount"] or "0") * 100).quantize(Decimal("1")))
        for row in statements
        for measurement in row["measurements"]
    )

    details = await async_client.get(
        f"/billing/seller-report/sellers/{seller_id}/details",
        headers=headers,
        params={
            "date_from": period_start.isoformat(),
            "date_to": period_end.isoformat(),
            "include_finance": "true",
        },
    )
    assert details.status_code == 200, details.text
    report = details.json()["storage_row"]
    invoice = await async_client.post(
        "/billing/invoices-v2/preview",
        headers=headers,
        json={
            "creation_mode": "selected_operations",
            "seller_id": str(seller_id),
            "date_from": period_start.isoformat(),
            "date_to": period_end.isoformat(),
            "selected_root_ids": [],
            "storage_calculation_token": report["calculation_token"],
        },
    )
    assert invoice.status_code == 200, invoice.text
    assert report["liter_days"] == pytest.approx(0.0098)
    assert report["amount_kopecks"] == invoice.json()["total_amount_kopecks"]
    assert allocated_kopecks == statement_kopecks
    assert statement_kopecks == report["amount_kopecks"] == invoice.json()["total_amount_kopecks"]


@pytest.mark.asyncio
async def test_fix_waits_for_dimensions_in_the_whole_seller_rounding_scope(
    async_client: AsyncClient,
) -> None:
    """P2: проводку нельзя фиксировать до расчёта всех складов продавца."""
    headers, _seller_id, _warehouse_ids, statement_ids = (
        await _create_cross_warehouse_fractional_storage_case(async_client)
    )
    async with SessionLocal() as session:
        second_statement = await session.get(StorageStatement, statement_ids[1])
        assert second_statement is not None
        second_measurement = await session.scalar(
            select(StorageMeasurement).where(
                StorageMeasurement.seller_id == second_statement.seller_id,
                StorageMeasurement.warehouse_id == second_statement.warehouse_id,
                StorageMeasurement.period_start == second_statement.period_start,
                StorageMeasurement.period_end == second_statement.period_end,
            )
        )
        assert second_measurement is not None
        second_measurement.status = "missing_dimensions"
        await session.commit()

    blocked = await async_client.post(
        f"/operations/storage/statements/{statement_ids[0]}/fix",
        headers=headers,
    )

    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["detail"] == "missing_dimensions"
    async with SessionLocal() as session:
        first_statement = await session.get(StorageStatement, statement_ids[0])
        assert first_statement is not None
        assert first_statement.status == "draft"
        ledger_count = await session.scalar(
            select(func.count(BillingLedgerEntry.id)).where(
                BillingLedgerEntry.source_type == "storage_measurement",
            )
        )
        assert ledger_count == 0


@pytest.mark.asyncio
async def test_warehouse_filter_preserves_cross_warehouse_fractional_allocation(
    async_client: AsyncClient,
) -> None:
    """A1-CR-004: a display filter must not become a pricing-scope filter."""
    headers, seller_id, warehouse_ids, statement_ids = (
        await _create_cross_warehouse_fractional_storage_case(async_client)
    )
    period_start = date(2026, 7, 1)
    period_end = date(2026, 7, 31)
    unfiltered_response = await async_client.get(
        "/operations/storage/statements",
        headers=headers,
        params={"year": 2026, "month": 7},
    )
    assert unfiltered_response.status_code == 200, unfiltered_response.text
    statement_ids_as_str = {str(statement_id) for statement_id in statement_ids}
    unfiltered = {
        row["warehouse_id"]: row
        for row in unfiltered_response.json()["statements"]
        if row["id"] in statement_ids_as_str
    }
    assert set(unfiltered) == {str(warehouse_id) for warehouse_id in warehouse_ids}

    for warehouse_id in warehouse_ids:
        filtered_response = await async_client.get(
            "/operations/storage/statements",
            headers=headers,
            params={"year": 2026, "month": 7, "warehouse_id": str(warehouse_id)},
        )
        assert filtered_response.status_code == 200, filtered_response.text
        filtered = [
            row
            for row in filtered_response.json()["statements"]
            if row["id"] in statement_ids_as_str
        ]
        assert len(filtered) == 1
        assert filtered[0]["warehouse_id"] == str(warehouse_id)
        # A warehouse filter only selects what the operator sees. It may not re-round it.
        assert filtered[0]["total_amount"] == unfiltered[str(warehouse_id)]["total_amount"]
        assert [
            (row["product_id"], row["amount"], row["rate_snapshot"])
            for row in filtered[0]["measurements"]
        ] == [
            (row["product_id"], row["amount"], row["rate_snapshot"])
            for row in unfiltered[str(warehouse_id)]["measurements"]
        ]

    unfiltered_kopecks = sum(
        int((Decimal(row["total_amount"]) * 100).quantize(Decimal("1")))
        for row in unfiltered.values()
    )
    details = await async_client.get(
        f"/billing/seller-report/sellers/{seller_id}/details",
        headers=headers,
        params={
            "date_from": period_start.isoformat(),
            "date_to": period_end.isoformat(),
            "include_finance": "true",
        },
    )
    assert details.status_code == 200, details.text
    report = details.json()["storage_row"]
    invoice = await async_client.post(
        "/billing/invoices-v2/preview",
        headers=headers,
        json={
            "creation_mode": "selected_operations",
            "seller_id": str(seller_id),
            "date_from": period_start.isoformat(),
            "date_to": period_end.isoformat(),
            "selected_root_ids": [],
            "storage_calculation_token": report["calculation_token"],
        },
    )
    assert invoice.status_code == 200, invoice.text
    assert (
        unfiltered_kopecks
        == report["amount_kopecks"]
        == invoice.json()["total_amount_kopecks"]
        == 1
    )


@pytest.mark.asyncio
async def test_cross_dated_tariff_history_returns_the_new_common_seller_pair(
    async_client: AsyncClient,
) -> None:
    """A1-CR-002: date A/B history cannot make the API return an older pair."""
    suffix = str(time.time_ns())
    headers, revision = await _admin(async_client, suffix)
    seller_id = await _seller(async_client, headers, f"Cross-dated seller {suffix}")
    created_warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "Cross dated", "code": f"cross-dated-{suffix}"},
    )
    assert created_warehouse.status_code == 200, created_warehouse.text
    warehouse_id = uuid.UUID(created_warehouse.json()["id"])
    start_a = datetime.now(MOSCOW).date()
    start_b = start_a + timedelta(days=1)

    async with SessionLocal() as session:
        warehouse = await session.get(Warehouse, warehouse_id)
        assert warehouse is not None
        tenant_id = warehouse.tenant_id
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name="Cross-dated product",
            sku_code=f"cross-dated-{suffix}",
            volume_liters=1,
            dimensions_source="manual",
        )
        session.add(product)
        await session.flush()
        event = ProductDimensionEvent(
            tenant_id=tenant_id,
            product_id=product.id,
            source="manual",
            observed_at=datetime.combine(start_b, datetime_time.min, MOSCOW),
            volume_liters=Decimal("1"),
            applied=True,
            fingerprint=f"cross-dated-event-{suffix}",
        )
        location = await get_or_create_sorting_location(session, tenant_id, warehouse_id)
        movement = InventoryMovement(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            storage_location_id=location.id,
            product_id=product.id,
            quantity_delta=1,
            movement_type="cross_dated_storage_test",
            created_at=datetime.combine(start_b, datetime_time.min, MOSCOW),
        )
        statement = StorageStatement(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            period_start=start_b,
            period_end=start_b,
            status="draft",
        )
        session.add_all(
            [
                event,
                movement,
                statement,
                BillingTariffVersionV2(
                    id=uuid.UUID(int=1),
                    tenant_id=tenant_id,
                    seller_id=None,
                    product_id=None,
                    employee_user_id=None,
                    service_code="storage",
                    unit="liter_day",
                    enabled=True,
                    rate=111,
                    valid_from_at=datetime.combine(start_b, datetime_time.min, MOSCOW).astimezone(
                        UTC
                    ),
                ),
                BillingTariffVersionV2(
                    id=uuid.UUID(int=2),
                    tenant_id=tenant_id,
                    seller_id=seller_id,
                    product_id=None,
                    employee_user_id=None,
                    service_code="storage",
                    unit="liter_day",
                    enabled=True,
                    rate=222,
                    valid_from_at=datetime.combine(start_a, datetime_time.min, MOSCOW).astimezone(
                        UTC
                    ),
                ),
            ]
        )
        await session.flush()
        statement_id = statement.id
        session.add(
            StorageMeasurement(
                tenant_id=tenant_id,
                seller_id=seller_id,
                warehouse_id=warehouse_id,
                product_id=product.id,
                dimension_event_id=event.id,
                movement_start_id=movement.id,
                movement_end_id=movement.id,
                period_start=start_b,
                period_end=start_b,
                quantity_days=Decimal("1"),
                liter_days=Decimal("1"),
                status="calculated",
            )
        )
        await session.commit()

    submitted = await async_client.post(
        "/operations/storage/tariffs",
        headers=headers,
        json={
            "revision": revision,
            "amount": "3.33",
            "valid_from": start_a.isoformat(),
            "seller_exception": {
                "seller_id": str(seller_id),
                "amount": "4.44",
                "valid_from": start_b.isoformat(),
            },
        },
    )
    assert submitted.status_code == 201, submitted.text
    body = submitted.json()
    async with SessionLocal() as session:
        new_common = await session.scalar(
            select(BillingTariffVersionV2).where(
                BillingTariffVersionV2.tenant_id == tenant_id,
                BillingTariffVersionV2.seller_id.is_(None),
                BillingTariffVersionV2.service_code == "storage",
                BillingTariffVersionV2.rate == 333,
            )
        )
        new_seller = await session.scalar(
            select(BillingTariffVersionV2).where(
                BillingTariffVersionV2.tenant_id == tenant_id,
                BillingTariffVersionV2.seller_id == seller_id,
                BillingTariffVersionV2.service_code == "storage",
                BillingTariffVersionV2.rate == 444,
            )
        )
    assert new_common is not None
    assert new_seller is not None
    assert body["warehouse_tariff"]["id"] == str(new_common.id)
    assert body["warehouse_tariff"]["amount"] == "3.33"
    assert body["warehouse_tariff"]["valid_from"] == start_a.isoformat()
    assert body["seller_exception"]["id"] == str(new_seller.id)
    assert body["seller_exception"]["amount"] == "4.44"
    assert body["seller_exception"]["valid_from"] == start_b.isoformat()
    repriced = next(
        row for row in body["recalculated_statements"] if row["id"] == str(statement_id)
    )
    assert repriced["measurements"][0]["rate_snapshot"] == "4.44"
