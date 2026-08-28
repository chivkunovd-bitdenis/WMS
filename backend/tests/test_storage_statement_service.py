from __future__ import annotations

import asyncio
import calendar
import time
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.api.storage import _apply_draft_pricing, _print_measurements, _rate_snapshot
from app.db.session import SessionLocal
from app.models.billing import BillingLedgerEntry, BillingTariffVersion, BillingTariffVersionV2
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.product_dimension_event import ProductDimensionEvent
from app.models.seller import Seller
from app.models.storage_measurement import StorageMeasurement
from app.models.storage_statement import StorageStatement
from app.models.warehouse import Warehouse
from app.services import storage_statement_service
from app.services.billing_seller_report_service import _storage_row
from app.services.sorting_location_service import get_or_create_sorting_location
from app.services.staff_packaging_billing_service import rub_to_kopecks
from app.services.storage_measurement_service import MOSCOW
from app.services.storage_statement_service import (
    StorageStatementError,
    _price_volume_segments,
    _statement_source_ids,
    _tariff_for_day,
    normalize_storage_ledger_quantity,
)


def _tariff(
    amount: str,
    valid_from: date,
    *,
    valid_to: date | None = None,
    seller_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
) -> BillingTariffVersionV2:
    return cast(
        BillingTariffVersionV2,
        SimpleNamespace(
            id=uuid.uuid4(),
            rate=rub_to_kopecks(Decimal(amount)),
            valid_from_at=datetime.combine(valid_from, datetime.min.time(), MOSCOW),
            valid_to_at=(
                datetime.combine(valid_to + timedelta(days=1), datetime.min.time(), MOSCOW)
                if valid_to is not None
                else None
            ),
            seller_id=seller_id,
            warehouse_id=warehouse_id,
        ),
    )


def test_zero_statement_uses_its_own_id_as_the_single_ledger_source() -> None:
    """A zero document never shares a nullable ledger source with another month."""
    statement = SimpleNamespace(id=uuid.uuid4())

    assert _statement_source_ids(statement, []) == {statement.id}


def test_measurement_statement_uses_each_measurement_as_its_ledger_source() -> None:
    statement = SimpleNamespace(id=uuid.uuid4())
    first = SimpleNamespace(id=uuid.uuid4())
    second = SimpleNamespace(id=uuid.uuid4())

    assert _statement_source_ids(statement, [first, second]) == {first.id, second.id}


def test_print_rows_do_not_pair_a_zero_ledger_entry_with_a_missing_sku() -> None:
    """TC-NEW-S11-08: zero statement printing is stable and has no phantom SKU."""
    zero_ledger = SimpleNamespace(source_id=uuid.uuid4())

    assert _print_measurements([], [zero_ledger]) == []


def test_print_row_uses_charged_ledger_quantity_instead_of_full_month_measurement() -> None:
    """A4 arithmetic stays consistent when a tariff starts after month start."""
    measurement_id = uuid.uuid4()
    product_id = uuid.uuid4()
    measurement = SimpleNamespace(
        id=measurement_id,
        product_id=product_id,
        product=SimpleNamespace(
            sku_code="MID-MONTH",
            wb_vendor_code="ARTICLE",
            volume_liters=Decimal("1"),
            dimensions_source="manual",
        ),
        dimension_event=None,
        liter_days=Decimal("31"),
    )
    ledger = SimpleNamespace(
        source_id=measurement_id,
        source_type="storage_measurement",
        service_code="storage_liter_day",
        unit="liter_day",
        quantity=Decimal("22"),
        rate=200,
        amount=4400,
    )

    [printed] = _print_measurements([measurement], [ledger])

    assert printed["liter_days"] == "22"
    assert printed["rate_snapshot"] == "2.00"
    assert printed["amount"] == "44.00"


def test_draft_rate_snapshot_does_not_expose_decimal_division_noise() -> None:
    measurement_id = uuid.uuid4()
    output = SimpleNamespace(
        measurements=[{"rate_snapshot": None, "liter_days": "0", "amount": None}],
        total_liter_days="0",
        total_amount="0",
    )
    measurement = SimpleNamespace(id=measurement_id)
    tariff = SimpleNamespace(amount=65)

    _apply_draft_pricing(
        output,
        [measurement],
        {
            measurement_id: (
                Decimal("125001.52"),
                Decimal("81250.98"),
                tariff,
            )
        },
    )

    assert output.measurements[0]["rate_snapshot"] == "0.65"


def test_storage_ledger_quantity_is_rounded_within_numeric_14_4() -> None:
    assert normalize_storage_ledger_quantity(Decimal("1.23456")) == Decimal("1.2346")
    assert normalize_storage_ledger_quantity(Decimal("9999999999.99994")) == Decimal(
        "9999999999.9999"
    )


@pytest.mark.parametrize(
    "quantity",
    [
        Decimal("9999999999.99995"),
        Decimal("-0.0001"),
        Decimal("Infinity"),
        Decimal("NaN"),
    ],
)
def test_storage_ledger_quantity_rejects_values_outside_numeric_14_4(
    quantity: Decimal,
) -> None:
    with pytest.raises(StorageStatementError, match=r"^ledger_quantity_out_of_range$"):
        normalize_storage_ledger_quantity(quantity)


def test_tariff_starting_mid_month_prices_only_forward() -> None:
    tariff = _tariff("2.00", date(2026, 7, 10))
    segments = [
        (
            datetime(2026, 7, 1, tzinfo=MOSCOW),
            datetime(2026, 8, 1, tzinfo=MOSCOW),
            1,
            Decimal("1"),
            None,
        )
    ]

    quantity, amount, snapshot = _price_volume_segments(segments, [tariff])

    assert quantity == Decimal("22")
    assert amount == Decimal("44.00")
    assert snapshot is tariff


def test_tariff_change_inside_month_uses_both_dated_rates() -> None:
    old = _tariff("1.00", date(2026, 7, 1), valid_to=date(2026, 7, 19))
    new = _tariff("2.00", date(2026, 7, 20))
    segments = [
        (
            datetime(2026, 7, 1, tzinfo=MOSCOW),
            datetime(2026, 8, 1, tzinfo=MOSCOW),
            1,
            Decimal("1"),
            None,
        )
    ]

    quantity, amount, snapshot = _price_volume_segments(segments, [old, new])

    assert quantity == Decimal("31")
    assert amount == Decimal("43.00")
    assert snapshot is new
    effective_rate = Decimal(
        _rate_snapshot((amount / quantity).quantize(Decimal("0.000000000001")))
    )
    assert (effective_rate * quantity).quantize(Decimal("0.01")) == amount


def test_seller_tariff_overrides_common_tariff_only_while_effective() -> None:
    seller_id = uuid.uuid4()
    common = _tariff("1.00", date(2026, 7, 1))
    personal = _tariff(
        "3.00",
        date(2026, 7, 10),
        valid_to=date(2026, 7, 20),
        seller_id=seller_id,
    )

    assert _tariff_for_day([common, personal], date(2026, 7, 9)) is common
    assert _tariff_for_day([common, personal], date(2026, 7, 10)) is personal
    assert _tariff_for_day([common, personal], date(2026, 7, 21)) is common


async def _seed_storage_statement(
    async_client: AsyncClient,
    *,
    status: str = "calculated",
    zero: bool = False,
    current_month: bool = False,
    with_tariff: bool = True,
) -> tuple[dict[str, str], uuid.UUID, uuid.UUID | None]:
    suffix = str(time.time_ns())
    registered = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Storage statement",
            "slug": f"storage-statement-{suffix}",
            "admin_email": f"storage-statement-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registered.status_code == 200, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    warehouse_response = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "Storage", "code": f"storage-{suffix}"},
    )
    assert warehouse_response.status_code == 200, warehouse_response.text
    warehouse_id = uuid.UUID(warehouse_response.json()["id"])
    today = datetime.now(MOSCOW).date()
    if current_month:
        period_start = today.replace(day=1)
    else:
        previous_end = today.replace(day=1) - timedelta(days=1)
        period_start = previous_end.replace(day=1)
    period_end = date(
        period_start.year,
        period_start.month,
        calendar.monthrange(period_start.year, period_start.month)[1],
    )

    measurement_id: uuid.UUID | None = None
    async with SessionLocal() as session:
        warehouse = await session.get(Warehouse, warehouse_id)
        assert warehouse is not None
        seller = Seller(tenant_id=warehouse.tenant_id, name=f"Seller {suffix}")
        session.add(seller)
        await session.flush()
        statement = StorageStatement(
            tenant_id=warehouse.tenant_id,
            seller_id=seller.id,
            warehouse_id=warehouse.id,
            period_start=period_start,
            period_end=period_end,
            status="draft",
        )
        session.add(statement)
        if with_tariff:
            session.add(
            BillingTariffVersionV2(
                tenant_id=warehouse.tenant_id,
                seller_id=None,
                product_id=None,
                employee_user_id=None,
                service_code="storage",
                unit="liter_day",
                enabled=True,
                rate=200,
                valid_from_at=datetime.combine(period_start, datetime.min.time(), MOSCOW),
                )
            )
        if not zero:
            product = Product(
                tenant_id=warehouse.tenant_id,
                seller_id=seller.id,
                name="Stored product",
                sku_code=f"STORAGE-{suffix}",
                volume_liters=1,
                dimensions_source="manual",
            )
            session.add(product)
            await session.flush()
            event = ProductDimensionEvent(
                tenant_id=warehouse.tenant_id,
                product_id=product.id,
                source="manual",
                observed_at=datetime.combine(period_start, datetime.min.time(), MOSCOW),
                volume_liters=Decimal("1"),
                applied=True,
                fingerprint=f"manual-{suffix}",
            )
            session.add(event)
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
                movement_type="storage_statement_test",
                created_at=datetime.combine(period_start, datetime.min.time(), MOSCOW),
            )
            session.add(movement)
            await session.flush()
            measurement = StorageMeasurement(
                tenant_id=warehouse.tenant_id,
                seller_id=seller.id,
                warehouse_id=warehouse.id,
                product_id=product.id,
                dimension_event_id=event.id,
                movement_start_id=movement.id,
                movement_end_id=movement.id,
                period_start=period_start,
                period_end=period_end,
                quantity_days=Decimal(period_end.day),
                liter_days=Decimal(period_end.day),
                status=status,
            )
            session.add(measurement)
            await session.flush()
            measurement_id = measurement.id
        await session.flush()
        statement_id = statement.id
        await session.commit()
        return headers, statement_id, measurement_id


@pytest.mark.asyncio
async def test_concurrent_fix_publishes_one_immutable_ledger_and_repeatable_print(
    async_client: AsyncClient,
) -> None:
    headers, statement_id, measurement_id = await _seed_storage_statement(async_client)
    assert measurement_id is not None

    first, second = await asyncio.gather(
        async_client.post(f"/operations/storage/statements/{statement_id}/fix", headers=headers),
        async_client.post(f"/operations/storage/statements/{statement_id}/fix", headers=headers),
    )

    assert {first.status_code, second.status_code} == {200}, (first.text, second.text)
    async with SessionLocal() as session:
        count = await session.scalar(
            select(func.count(BillingLedgerEntry.id)).where(
                BillingLedgerEntry.source_type == "storage_measurement",
                BillingLedgerEntry.source_id == measurement_id,
            )
        )
        assert count == 1

    first_print = await async_client.get(
        f"/operations/storage/statements/{statement_id}/print", headers=headers
    )
    async with SessionLocal() as session:
        measurement = await session.get(StorageMeasurement, measurement_id)
        assert measurement is not None
        product = await session.get(Product, measurement.product_id)
        old_event = await session.get(ProductDimensionEvent, measurement.dimension_event_id)
        assert product is not None and old_event is not None
        old_event.applied = False
        product.volume_liters = 99
        session.add(
            ProductDimensionEvent(
                tenant_id=measurement.tenant_id,
                product_id=measurement.product_id,
                source="manual",
                observed_at=datetime.now(MOSCOW),
                volume_liters=Decimal("99"),
                applied=True,
                fingerprint=f"manual-after-fix-{time.time_ns()}",
            )
        )
        await session.commit()
    second_print = await async_client.get(
        f"/operations/storage/statements/{statement_id}/print", headers=headers
    )
    assert first_print.status_code == second_print.status_code == 200
    assert first_print.json() == second_print.json()
    payload = first_print.json()
    assert payload["status"] == "fixed"
    assert payload["fixed_at"]
    assert payload["measurements"][0]["rate_snapshot"] == "2.00"
    assert payload["measurements"][0]["liter_days"] == payload["total_liter_days"]
    assert payload["measurements"][0]["service_code"] == "storage"
    assert payload["measurements"][0]["unit"] == "liter_day"
    period_start = date.fromisoformat(payload["period_start"])
    listed = await async_client.get(
        "/operations/storage/statements",
        headers=headers,
        params={"year": period_start.year, "month": period_start.month},
    )
    assert listed.status_code == 200
    assert listed.json()["tariff_configured"] is True
    listed_statement = next(
        row for row in listed.json()["statements"] if row["id"] == str(statement_id)
    )
    assert listed_statement["total_amount"] == payload["total_amount"]
    assert listed_statement["measurements"] == payload["measurements"]

    second_warehouse = await async_client.post(
        "/warehouses",
        headers=headers,
        json={"name": "Storage without common tariff", "code": f"storage-2-{time.time_ns()}"},
    )
    assert second_warehouse.status_code == 200, second_warehouse.text
    second_warehouse_id = uuid.UUID(second_warehouse.json()["id"])
    without_tariff = await async_client.get(
        "/operations/storage/statements",
        headers=headers,
        params={
            "year": period_start.year,
            "month": period_start.month,
            "warehouse_id": second_warehouse_id,
        },
    )
    assert without_tariff.status_code == 200
    assert without_tariff.json()["tariff_configured"] is True

    async with SessionLocal() as session:
        statement = await session.get(StorageStatement, statement_id)
        assert statement is not None
        session.add(
            BillingTariffVersion(
                tenant_id=statement.tenant_id,
                seller_id=statement.seller_id,
                warehouse_id=second_warehouse_id,
                service_code="storage_liter_day",
                unit="liter_day",
                amount=700,
                valid_from=period_start,
            )
        )
        await session.commit()
    personal_only = await async_client.get(
        "/operations/storage/statements",
        headers=headers,
        params={
            "year": period_start.year,
            "month": period_start.month,
            "warehouse_id": second_warehouse_id,
        },
    )
    assert personal_only.status_code == 200
    assert personal_only.json()["tariff_configured"] is True


@pytest.mark.asyncio
async def test_problem_current_month_and_zero_statement_fix_rules(
    async_client: AsyncClient,
) -> None:
    problem_headers, problem_id, _ = await _seed_storage_statement(
        async_client, status="missing_dimensions"
    )
    problem = await async_client.post(
        f"/operations/storage/statements/{problem_id}/fix", headers=problem_headers
    )
    assert problem.status_code == 409
    assert problem.json()["detail"] == "missing_dimensions"

    current_headers, current_id, _ = await _seed_storage_statement(async_client, current_month=True)
    current = await async_client.post(
        f"/operations/storage/statements/{current_id}/fix", headers=current_headers
    )
    assert current.status_code == 409
    assert current.json()["detail"] == "period_not_closed"

    zero_headers, zero_id, _ = await _seed_storage_statement(async_client, zero=True)
    zero = await async_client.post(
        f"/operations/storage/statements/{zero_id}/fix", headers=zero_headers
    )
    assert zero.status_code == 200, zero.text
    assert zero.json()["measurements"] == []
    assert zero.json()["total_amount"] == "0.00"
    async with SessionLocal() as session:
        ledger = await session.scalar(
            select(BillingLedgerEntry).where(BillingLedgerEntry.source_id == zero_id)
        )
        assert ledger is not None
    assert ledger.quantity == 0
    assert ledger.amount == 0

    no_tariff_headers, no_tariff_id, _ = await _seed_storage_statement(
        async_client, with_tariff=False
    )
    unrelated_warehouse = await async_client.post(
        "/warehouses",
        headers=no_tariff_headers,
        json={"name": "Unrelated storage", "code": f"unrelated-{time.time_ns()}"},
    )
    assert unrelated_warehouse.status_code == 200, unrelated_warehouse.text
    async with SessionLocal() as session:
        statement = await session.get(StorageStatement, no_tariff_id)
        assert statement is not None
        session.add(
            BillingTariffVersion(
                tenant_id=statement.tenant_id,
                seller_id=None,
                warehouse_id=uuid.UUID(unrelated_warehouse.json()["id"]),
                service_code="storage_liter_day",
                unit="liter_day",
                amount=900,
                valid_from=statement.period_start,
            )
        )
        await session.commit()
    no_tariff = await async_client.post(
        f"/operations/storage/statements/{no_tariff_id}/fix", headers=no_tariff_headers
    )
    assert no_tariff.status_code == 409
    assert no_tariff.json()["detail"] == "tariff_not_found"


@pytest.mark.asyncio
async def test_statement_uses_the_same_seller_override_as_the_invoice_report(
    async_client: AsyncClient,
) -> None:
    """TC-NEW-A1-001/002: a deliberately different legacy rate cannot affect storage."""
    _headers, statement_id, measurement_id = await _seed_storage_statement(async_client)
    assert measurement_id is not None
    async with SessionLocal() as session:
        statement = await session.get(StorageStatement, statement_id)
        assert statement is not None
        session.add_all(
            [
                # This was the old statement source.  Its wildly different rate
                # must not leak into either financial calculation.
                BillingTariffVersion(
                    tenant_id=statement.tenant_id,
                    seller_id=None,
                    warehouse_id=statement.warehouse_id,
                    service_code="storage_liter_day",
                    unit="liter_day",
                    amount=9900,
                    valid_from=statement.period_start,
                ),
                BillingTariffVersionV2(
                    tenant_id=statement.tenant_id,
                    seller_id=statement.seller_id,
                    product_id=None,
                    employee_user_id=None,
                    service_code="storage",
                    unit="liter_day",
                    enabled=True,
                    rate=300,
                    valid_from_at=datetime.combine(
                        statement.period_start, datetime.min.time(), MOSCOW
                    ),
                ),
            ]
        )
        await session.commit()
        measurements = list(
            (
                await session.scalars(
                    select(StorageMeasurement).where(StorageMeasurement.id == measurement_id)
                )
            ).all()
        )
        pricing = await storage_statement_service.get_storage_draft_pricing(
            session, statement, measurements
        )
        report = await _storage_row(
            session,
            tenant_id=statement.tenant_id,
            seller_id=statement.seller_id,
            date_from=statement.period_start,
            date_to=statement.period_end,
            start=datetime.combine(statement.period_start, datetime.min.time(), MOSCOW),
            end=datetime.combine(
                statement.period_end + timedelta(days=1), datetime.min.time(), MOSCOW
            ),
            include_finance=True,
        )
    statement_kopecks = sum(
        int((amount * 100).quantize(Decimal("1")))
        for _, amount, _ in pricing.values()
    )
    assert statement_kopecks == report["amount_kopecks"]
    assert {tariff.rate for _, _, tariff in pricing.values()} == {300}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("quantity", "amount", "detail"),
    [
        (Decimal("10000000000"), Decimal("1"), "ledger_quantity_out_of_range"),
        (Decimal("0.1"), Decimal("10000000"), "ledger_rate_out_of_range"),
        (Decimal("10000000"), Decimal("30000000"), "ledger_amount_out_of_range"),
    ],
)
async def test_fix_rejects_unrepresentable_ledger_values_without_partial_state(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    quantity: Decimal,
    amount: Decimal,
    detail: str,
) -> None:
    headers, statement_id, measurement_id = await _seed_storage_statement(async_client)
    assert measurement_id is not None

    async def invalid_pricing(
        _session: object,
        _statement: StorageStatement,
        measurements: list[StorageMeasurement],
        tariffs: list[BillingTariffVersionV2],
    ) -> dict[uuid.UUID, tuple[Decimal, Decimal, BillingTariffVersionV2]]:
        assert [row.id for row in measurements] == [measurement_id]
        return {measurement_id: (quantity, amount, tariffs[0])}

    monkeypatch.setattr(storage_statement_service, "_measurement_pricing", invalid_pricing)

    response = await async_client.post(
        f"/operations/storage/statements/{statement_id}/fix",
        headers=headers,
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"] == detail
    async with SessionLocal() as session:
        statement = await session.get(StorageStatement, statement_id)
        assert statement is not None
        assert statement.status == "draft"
        ledger_count = await session.scalar(
            select(func.count(BillingLedgerEntry.id)).where(
                BillingLedgerEntry.source_type == "storage_measurement",
                BillingLedgerEntry.source_id == measurement_id,
            )
        )
    assert ledger_count == 0
