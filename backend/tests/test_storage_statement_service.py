from __future__ import annotations

import calendar
import time
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import pytest
from httpx import AsyncClient

from app.api.storage import StorageStatementOut, _apply_night_charges, _print_measurements
from app.db.session import SessionLocal
from app.models.billing import BillingTariffVersion, BillingTariffVersionV2
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.product_dimension_event import ProductDimensionEvent
from app.models.seller import Seller
from app.models.storage_measurement import StorageMeasurement
from app.models.storage_statement import StorageStatement
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services.billing_seller_report_service import _storage_row
from app.services.sorting_location_service import get_or_create_sorting_location
from app.services.storage_daily_charge_service import charge_storage_day
from app.services.storage_measurement_service import MOSCOW
from app.services.storage_statement_service import (
    StorageNightCharge,
    StorageStatementError,
    _statement_source_ids,
    normalize_storage_ledger_quantity,
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
            name="Товар середины месяца",
            wb_vendor_code="ARTICLE",
            volume_liters=Decimal("1"),
            dimensions_source="manual",
            length_mm=100,
            width_mm=200,
            height_mm=50,
        ),
        dimension_event=None,
        liter_days=Decimal("31"),
        quantity_days=Decimal("31"),
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
    assert printed["dimensions_mm"] == [100, 200, 50]
    assert printed["quantity_days"] == "31"
    assert printed["rate_snapshot"] == "2.00"
    assert printed["amount"] == "44.00"


def test_night_rate_snapshot_does_not_expose_decimal_division_noise() -> None:
    """Фактическая ставка — деньги на литро-дни, и делить надо без хвоста."""
    product_id = uuid.uuid4()
    output = SimpleNamespace(
        measurements=[{"rate_snapshot": None, "liter_days": None, "amount": None}],
        total_liter_days=None,
        total_amount=None,
    )
    measurement = SimpleNamespace(product_id=product_id)

    _apply_night_charges(
        cast(StorageStatementOut, output),
        [cast(StorageMeasurement, measurement)],
        {
            product_id: StorageNightCharge(
                liter_days=Decimal("125001.52"),
                amount_kopecks=8_125_098,
            )
        },
    )

    assert output.measurements[0]["rate_snapshot"] == "0.65"
    assert output.measurements[0]["amount"] == "81250.98"
    assert output.total_amount == "81250.98"


def test_night_charge_without_a_rate_shows_liter_days_but_no_money() -> None:
    """Сутки без ставки — это литро-дни без денег, а не бесплатное хранение."""
    product_id = uuid.uuid4()
    output = SimpleNamespace(
        measurements=[{"rate_snapshot": None, "liter_days": None, "amount": None}],
        total_liter_days=None,
        total_amount=None,
    )
    measurement = SimpleNamespace(product_id=product_id)

    _apply_night_charges(
        cast(StorageStatementOut, output),
        [cast(StorageMeasurement, measurement)],
        {product_id: StorageNightCharge(liter_days=Decimal("3"), amount_kopecks=None)},
    )

    assert output.total_liter_days == "3"
    assert output.measurements[0]["amount"] is None
    assert output.total_amount is None


def test_product_without_night_charges_keeps_the_dash() -> None:
    """Ночь по товару не проходила — показываем прочерк, а не выдуманный ноль."""
    output = SimpleNamespace(
        measurements=[{"rate_snapshot": None, "liter_days": None, "amount": None}],
        total_liter_days=None,
        total_amount=None,
    )
    measurement = SimpleNamespace(product_id=uuid.uuid4())

    _apply_night_charges(
        cast(StorageStatementOut, output), [cast(StorageMeasurement, measurement)], {}
    )

    assert output.measurements[0]["liter_days"] is None
    assert output.total_liter_days is None
    assert output.total_amount is None


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


async def _seed_storage_statement(
    async_client: AsyncClient,
    *,
    status: str = "calculated",
    zero: bool = False,
    current_month: bool = False,
    with_tariff: bool = True,
    charged_days: int = 1,
) -> tuple[dict[str, str], uuid.UUID, uuid.UUID | None]:
    """Расчёт хранения за месяц плюс ночные начисления за первые его сутки.

    Без начислений на экране честно нечего показывать: деньги за хранение пишет
    только ночная задача, и тест обязан пройти тем же путём, что и продакшен.
    """
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
        tenant = await session.get(Tenant, warehouse.tenant_id)
        assert tenant is not None
        tenant.billing_enabled_from = period_start
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
        tenant_id = warehouse.tenant_id
        await session.commit()

    for offset in range(charged_days):
        async with SessionLocal() as session:
            await charge_storage_day(session, tenant_id, day=period_start + timedelta(days=offset))
    return headers, statement_id, measurement_id


@pytest.mark.asyncio
async def test_draft_calculation_prints_and_lists_the_same_numbers(
    async_client: AsyncClient,
) -> None:
    """Печать работает без фиксации и совпадает со списком.

    Фиксация расчёта убрана: деньги за хранение пишет ночная задача, а не
    человек. Печать при этом осталась нужна — она показывает то же самое, что и
    таблица на экране, теми же цифрами из тех же начислений.
    """
    headers, statement_id, measurement_id = await _seed_storage_statement(async_client)
    assert measurement_id is not None

    printed = await async_client.get(
        f"/operations/storage/statements/{statement_id}/print", headers=headers
    )
    assert printed.status_code == 200, printed.text
    payload = printed.json()
    assert payload["status"] == "draft"
    # Ночь начислила одни сутки: литр объёма по ставке 2 рубля за литро-день.
    assert payload["measurements"][0]["liter_days"] == "1.0000"
    assert payload["measurements"][0]["rate_snapshot"] == "2.00"
    assert payload["measurements"][0]["amount"] == "2.00"
    assert payload["measurements"][0]["liter_days"] == payload["total_liter_days"]
    assert payload["total_amount"] == "2.00"

    # Ручная фиксация больше не существует как операция.
    removed = await async_client.post(
        f"/operations/storage/statements/{statement_id}/fix", headers=headers
    )
    assert removed.status_code == 404

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


@pytest.mark.asyncio
async def test_screen_shows_no_money_until_the_night_has_charged(
    async_client: AsyncClient,
) -> None:
    """Обмер есть, ночь ещё не проходила — в деньгах прочерк, а не ноль.

    Ноль в этой клетке читался бы как «хранение бесплатно». Прочерк честно
    говорит: за эти сутки ещё не начисляли.
    """
    headers, statement_id, measurement_id = await _seed_storage_statement(
        async_client, charged_days=0
    )
    assert measurement_id is not None

    printed = await async_client.get(
        f"/operations/storage/statements/{statement_id}/print", headers=headers
    )
    assert printed.status_code == 200, printed.text
    payload = printed.json()

    assert payload["total_amount"] is None
    assert payload["total_liter_days"] is None
    assert payload["measurements"][0]["liter_days"] is None
    assert payload["measurements"][0]["amount"] is None
    assert payload["measurements"][0]["rate_snapshot"] is None
    # Операционная часть строки при этом на месте: печатать расчёт всё равно надо.
    assert payload["measurements"][0]["volume_liters"] == "1.000000"
    assert payload["measurements"][0]["status"] == "calculated"


@pytest.mark.asyncio
async def test_screen_and_report_show_the_same_seller_rate_from_the_night(
    async_client: AsyncClient,
) -> None:
    """TC-NEW-A1-001/002: экран и отчёт читают одни начисления, ставка селлера бьёт общую.

    Экран отбирает начисления по ключу суток, отчёт — по моменту начисления;
    запросы разные, значит совпадение цифр действительно что-то доказывает.
    Старая складская ставка 99 рублей намеренно лежит рядом: она историческая и
    не имеет права попасть ни в одну из них.
    """
    headers, statement_id, measurement_id = await _seed_storage_statement(
        async_client, charged_days=0
    )
    assert measurement_id is not None
    async with SessionLocal() as session:
        statement = await session.get(StorageStatement, statement_id)
        assert statement is not None
        session.add_all(
            [
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
        tenant_id = statement.tenant_id
        seller_id = statement.seller_id
        period_start = statement.period_start
        period_end = statement.period_end

    for offset in (0, 1):
        async with SessionLocal() as session:
            await charge_storage_day(session, tenant_id, day=period_start + timedelta(days=offset))

    listed = await async_client.get(
        "/operations/storage/statements",
        headers=headers,
        params={"year": period_start.year, "month": period_start.month},
    )
    assert listed.status_code == 200, listed.text
    screen = next(
        row for row in listed.json()["statements"] if row["id"] == str(statement_id)
    )

    async with SessionLocal() as session:
        report = await _storage_row(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            date_from=period_start,
            date_to=period_end,
            start=datetime.combine(period_start, datetime.min.time(), MOSCOW),
            end=datetime.combine(period_end + timedelta(days=1), datetime.min.time(), MOSCOW),
            include_finance=True,
        )

    screen_kopecks = int((Decimal(screen["total_amount"]) * 100).quantize(Decimal("1")))
    assert screen_kopecks == report["amount_kopecks"] == 600
    assert screen["measurements"][0]["rate_snapshot"] == "3.00"
