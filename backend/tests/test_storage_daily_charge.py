"""Ночное начисление за хранение: литро-дни прошедших суток."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.billing import BillingLedgerEntry, BillingTariffVersionV2
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.product_dimension_event import ProductDimensionEvent
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services.sorting_location_service import get_or_create_sorting_location
from app.services.storage_daily_charge_service import (
    charge_storage_day,
    missing_charge_days,
    previous_moscow_day,
)
from app.services.storage_measurement_service import MOSCOW


async def _seed(
    async_client: AsyncClient,
    *,
    common_rate: int | None = 200,
    seller_rate: int | None = None,
    billing_enabled: bool = True,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Арендатор с одной штукой товара объёмом литр, лежащей на складе."""
    suffix = str(time.time_ns())
    registered = await async_client.post(
        "/auth/register",
        json={
            "organization_name": "Storage daily",
            "slug": f"storage-daily-{suffix}",
            "admin_email": f"storage-daily-{suffix}@example.com",
            "password": "password123",
        },
    )
    assert registered.status_code == 200, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    warehouse_response = await async_client.post(
        "/warehouses", headers=headers, json={"name": "Daily", "code": f"daily-{suffix}"}
    )
    assert warehouse_response.status_code == 200, warehouse_response.text
    warehouse_id = uuid.UUID(warehouse_response.json()["id"])

    day = previous_moscow_day()
    long_before = datetime.combine(day - timedelta(days=30), datetime.min.time(), MOSCOW)

    async with SessionLocal() as session:
        warehouse = await session.get(Warehouse, warehouse_id)
        assert warehouse is not None
        tenant_id = warehouse.tenant_id
        tenant = await session.get(Tenant, tenant_id)
        assert tenant is not None
        tenant.billing_enabled_from = (day - timedelta(days=60)) if billing_enabled else None
        seller = Seller(tenant_id=tenant_id, name=f"Seller {suffix}")
        session.add(seller)
        await session.flush()
        product = Product(
            tenant_id=tenant_id,
            seller_id=seller.id,
            name="Stored product",
            sku_code=f"DAILY-{suffix}",
            volume_liters=1,
            dimensions_source="manual",
        )
        session.add(product)
        await session.flush()
        session.add(
            ProductDimensionEvent(
                tenant_id=tenant_id,
                product_id=product.id,
                source="manual",
                observed_at=long_before,
                volume_liters=Decimal("1"),
                applied=True,
                fingerprint=f"manual-{suffix}",
            )
        )
        location = await get_or_create_sorting_location(session, tenant_id, warehouse.id)
        session.add(
            InventoryMovement(
                tenant_id=tenant_id,
                seller_id=seller.id,
                warehouse_id=warehouse.id,
                storage_location_id=location.id,
                product_id=product.id,
                quantity_delta=1,
                movement_type="storage_daily_test",
                created_at=long_before,
            )
        )
        for rate, scoped_seller in ((common_rate, None), (seller_rate, seller.id)):
            if rate is None:
                continue
            session.add(
                BillingTariffVersionV2(
                    tenant_id=tenant_id,
                    seller_id=scoped_seller,
                    product_id=None,
                    employee_user_id=None,
                    service_code="storage",
                    unit="liter_day",
                    enabled=True,
                    rate=rate,
                    valid_from_at=long_before,
                )
            )
        await session.commit()
        return tenant_id, seller.id, product.id


async def _storage_entries(tenant_id: uuid.UUID) -> list[BillingLedgerEntry]:
    async with SessionLocal() as session:
        return list(
            (
                await session.scalars(
                    select(BillingLedgerEntry).where(
                        BillingLedgerEntry.tenant_id == tenant_id,
                        BillingLedgerEntry.service_code == "storage",
                    )
                )
            ).all()
        )


@pytest.mark.asyncio
async def test_nightly_run_charges_one_row_per_product_and_repeats_safely(
    async_client: AsyncClient,
) -> None:
    """Сутки хранения одной литровой штуки — один литро-день по общей ставке.

    Повтор задачи за те же сутки не должен создавать вторую строку: ночной
    прогон могут запустить дважды, и селлер не обязан платить за это дважды.
    """
    tenant_id, seller_id, _product_id = await _seed(async_client)
    day = previous_moscow_day()

    async with SessionLocal() as session:
        created = await charge_storage_day(session, tenant_id, day=day)
    assert created == 1

    entries = await _storage_entries(tenant_id)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.seller_id == seller_id
    assert entry.unit == "liter_day"
    assert entry.source_type == "storage_day"
    assert entry.event_kind == f"storage_day:{day.isoformat()}"
    assert entry.quantity == Decimal("1.0000")
    assert entry.rate == 200
    assert entry.amount == 200
    # Начисление принадлежит своим суткам, а не моменту запуска задачи.
    assert entry.occurred_at.astimezone(MOSCOW).date() == day

    async with SessionLocal() as session:
        repeated = await charge_storage_day(session, tenant_id, day=day)
    assert repeated == 0
    assert len(await _storage_entries(tenant_id)) == 1


@pytest.mark.asyncio
async def test_seller_rate_beats_the_common_one(async_client: AsyncClient) -> None:
    """Своя ставка селлера перебивает общую — тот же приоритет, что у операций."""
    tenant_id, _seller_id, _product_id = await _seed(
        async_client, common_rate=200, seller_rate=350
    )

    async with SessionLocal() as session:
        await charge_storage_day(session, tenant_id, day=previous_moscow_day())

    entries = await _storage_entries(tenant_id)
    assert len(entries) == 1
    assert entries[0].rate == 350
    assert entries[0].amount == 350


@pytest.mark.asyncio
async def test_missing_rate_leaves_a_visible_unpriced_row(async_client: AsyncClient) -> None:
    """Без ставки строка всё равно есть: дыра должна быть видна, а не пропасть."""
    tenant_id, _seller_id, _product_id = await _seed(async_client, common_rate=None)

    async with SessionLocal() as session:
        await charge_storage_day(session, tenant_id, day=previous_moscow_day())

    entries = await _storage_entries(tenant_id)
    assert len(entries) == 1
    assert entries[0].quantity == Decimal("1.0000")
    assert entries[0].rate is None
    assert entries[0].amount is None


@pytest.mark.asyncio
async def test_tenant_without_billing_start_date_is_not_charged(
    async_client: AsyncClient,
) -> None:
    """Пока дата начала биллинга не проставлена, склад не стоит денег."""
    tenant_id, _seller_id, _product_id = await _seed(async_client, billing_enabled=False)

    async with SessionLocal() as session:
        created = await charge_storage_day(session, tenant_id, day=previous_moscow_day())

    assert created == 0
    assert await _storage_entries(tenant_id) == []


@pytest.mark.asyncio
async def test_report_takes_storage_from_the_nightly_charges(
    async_client: AsyncClient,
) -> None:
    """Отчёт показывает то, что записала ночь, а не считает литро-дни заново.

    Раньше экран пересчитывал хранение по движениям при каждом открытии, а
    ночные начисления не читал никто. Две правды об одних и тех же сутках —
    спор, в котором нельзя победить: источник должен быть один.
    """
    from app.services.billing_seller_report_service import _storage_row, moscow_interval

    tenant_id, seller_id, _product_id = await _seed(async_client)
    day = previous_moscow_day()
    async with SessionLocal() as session:
        assert await charge_storage_day(session, tenant_id, day=day) == 1

    start, end = moscow_interval(day, day)
    async with SessionLocal() as session:
        row = await _storage_row(
            session, tenant_id=tenant_id, seller_id=seller_id,
            date_from=day, date_to=day, start=start, end=end, include_finance=True,
        )

    assert row["liter_days"] == pytest.approx(1.0)
    assert row["amount_kopecks"] == 200
    assert row["status"] == "calculated"
    # Подписанного токена больше нет: цену даёт начисление, а не подпись запроса.
    assert "calculation_token" not in row


@pytest.mark.asyncio
async def test_missed_night_is_charged_on_the_next_run(async_client: AsyncClient) -> None:
    """Пропущенная ночь не теряется: следующий проход добирает её сам.

    Хранение — деньги. Если воркер лежал или выкатка затянулась, за те сутки
    иначе не заплатят никогда: повторно их никто не посчитает.
    """
    tenant_id, _seller_id, _product_id = await _seed(async_client)
    yesterday = previous_moscow_day()
    before = yesterday - timedelta(days=2)

    async with SessionLocal() as session:
        pending = await missing_charge_days(session, tenant_id, until=yesterday)
    assert before in pending and yesterday in pending

    async with SessionLocal() as session:
        assert await charge_storage_day(session, tenant_id, day=before) == 1

    # Посчитанные сутки остаются в списке пересмотра: по одной строке нельзя
    # понять, все ли товары за них посчитаны. Второй проход по ним ничего не
    # задваивает — строка адресуется складом, товаром и датой.
    async with SessionLocal() as session:
        pending_after = await missing_charge_days(session, tenant_id, until=yesterday)
    assert before in pending_after and yesterday in pending_after

    async with SessionLocal() as session:
        assert await charge_storage_day(session, tenant_id, day=before) == 0
    assert len([row for row in await _storage_entries(tenant_id)]) == 1


@pytest.mark.asyncio
async def test_product_measured_later_is_charged_for_the_days_it_was_missed(
    async_client: AsyncClient,
) -> None:
    """Товар без обмера не теряет прошлые сутки: обмер внесли — ночь их добрала.

    Раньше сутки считались закрытыми по первой же строке арендатора. Товар,
    пропущенный из-за отсутствующих габаритов, не пересчитывался никогда, хотя
    лежал на складе и место занимал.
    """
    tenant_id, seller_id, _product_id = await _seed(async_client)
    yesterday = previous_moscow_day()
    day = yesterday - timedelta(days=3)
    long_before = datetime.combine(day - timedelta(days=10), datetime.min.time(), MOSCOW)

    async with SessionLocal() as session:
        warehouse_id = await session.scalar(
            select(Warehouse.id).where(Warehouse.tenant_id == tenant_id)
        )
        assert warehouse_id is not None
        # Второй товар лежит рядом с первым, но обмера у него нет.
        unmeasured = Product(
            tenant_id=tenant_id,
            seller_id=seller_id,
            name="Unmeasured product",
            sku_code=f"NODIM-{uuid.uuid4().hex[:8]}",
            dimensions_source="manual",
        )
        session.add(unmeasured)
        await session.flush()
        location = await get_or_create_sorting_location(session, tenant_id, warehouse_id)
        session.add(
            InventoryMovement(
                tenant_id=tenant_id,
                seller_id=seller_id,
                warehouse_id=warehouse_id,
                storage_location_id=location.id,
                product_id=unmeasured.id,
                quantity_delta=1,
                movement_type="storage_daily_test",
                created_at=long_before,
            )
        )
        await session.commit()
        unmeasured_id = unmeasured.id

    # Ночь считает эти сутки: посчитан только товар с обмером.
    async with SessionLocal() as session:
        assert await charge_storage_day(session, tenant_id, day=day) == 1

    # Оператор вносит габариты задним числом.
    async with SessionLocal() as session:
        session.add(
            ProductDimensionEvent(
                tenant_id=tenant_id,
                product_id=unmeasured_id,
                source="manual",
                observed_at=long_before,
                volume_liters=Decimal("2"),
                applied=True,
                fingerprint=f"manual-late-{uuid.uuid4().hex[:8]}",
            )
        )
        product = await session.get(Product, unmeasured_id)
        assert product is not None
        product.volume_liters = 2
        await session.commit()

    async with SessionLocal() as session:
        pending = await missing_charge_days(session, tenant_id, until=yesterday)
    assert day in pending

    # Следующая ночь дописывает пропущенный товар и не трогает уже посчитанный.
    async with SessionLocal() as session:
        assert await charge_storage_day(session, tenant_id, day=day) == 1
    charged_products = {
        row.source_id
        for row in await _storage_entries(tenant_id)
        if row.event_kind == f"storage_day:{day.isoformat()}"
    }
    assert len(charged_products) == 2


@pytest.mark.asyncio
async def test_partially_measured_day_is_topped_up_after_later_measurement(
    async_client: AsyncClient,
) -> None:
    """Сутки, посчитанные наполовину, дописываются, когда обмер внесли позже.

    Товар лежал весь день, но объём стал известен только к середине. Первая ночь
    начисляла часть, а любой следующий проход видел существующую строку и
    пропускал сутки навсегда — это систематическая недоплата за хранение.
    """
    tenant_id, _seller_id, _product_id = await _seed(async_client)
    day = previous_moscow_day()

    async with SessionLocal() as session:
        assert await charge_storage_day(session, tenant_id, day=day) == 1
    full = (await _storage_entries(tenant_id))[0].quantity

    # Изображаем частично посчитанные сутки: строка есть, но меньше правды —
    # ровно то, что оставляет за собой день с поздним обмером.
    async with SessionLocal() as session:
        row = (
            await session.scalars(
                select(BillingLedgerEntry).where(
                    BillingLedgerEntry.tenant_id == tenant_id,
                    BillingLedgerEntry.service_code == "storage",
                )
            )
        ).one()
        row.quantity = full / 2
        await session.commit()

    async with SessionLocal() as session:
        assert await charge_storage_day(session, tenant_id, day=day) == 1

    after = await _storage_entries(tenant_id)
    # Строка одна и та же, дописана до полной: второй строки за те же сутки нет.
    assert len(after) == 1
    assert after[0].quantity == full


@pytest.mark.asyncio
async def test_repeat_pass_never_reduces_an_existing_charge(
    async_client: AsyncClient,
) -> None:
    """Повторный проход не уменьшает уже начисленное.

    Начисление — событие, а не черновик: если пересчёт вдруг даст меньше,
    переписывать деньги вниз нельзя.
    """
    tenant_id, _seller_id, product_id = await _seed(async_client)
    day = previous_moscow_day()

    async with SessionLocal() as session:
        assert await charge_storage_day(session, tenant_id, day=day) == 1
    was = (await _storage_entries(tenant_id))[0].quantity

    async with SessionLocal() as session:
        product = await session.get(Product, product_id)
        assert product is not None
        product.volume_liters = 1
        await session.commit()

    async with SessionLocal() as session:
        assert await charge_storage_day(session, tenant_id, day=day) == 0
    assert (await _storage_entries(tenant_id))[0].quantity == was


@pytest.mark.asyncio
async def test_invoiced_day_is_topped_up_by_a_separate_line(
    async_client: AsyncClient,
) -> None:
    """Уже выставленное начисление не переписывается — разница идёт отдельной строкой.

    Счёт запоминает свою сумму и помечает строку израсходованной: второй раз в
    счёт она не пойдёт. Если дописать её на месте, доначисленные деньги не
    выставят никогда, а отчёт разойдётся со счётом. Поэтому недостающее
    добавляется соседней строкой за те же сутки — её счёт увидит как новую.
    """
    from app.models.billing import (
        BillingInvoiceV2,
        BillingInvoiceV2Line,
        BillingInvoiceV2Source,
    )

    tenant_id, seller_id, _product_id = await _seed(async_client)
    day = previous_moscow_day()

    async with SessionLocal() as session:
        assert await charge_storage_day(session, tenant_id, day=day) == 1
    full = (await _storage_entries(tenant_id))[0].quantity

    async with SessionLocal() as session:
        row = (
            await session.scalars(
                select(BillingLedgerEntry).where(
                    BillingLedgerEntry.tenant_id == tenant_id,
                    BillingLedgerEntry.service_code == "storage",
                )
            )
        ).one()
        row.quantity = full / 2
        invoice = BillingInvoiceV2(
            tenant_id=tenant_id,
            seller_id=seller_id,
            number="TEST-1",
            period_start=day,
            period_end=day,
            total_amount_kopecks=0,
            status="issued",
            creation_mode="selected_operations",
        )
        session.add(invoice)
        await session.flush()
        line = BillingInvoiceV2Line(
            tenant_id=tenant_id,
            invoice_id=invoice.id,
            description_snapshot="Хранение",
            unit_price_kopecks=None,
            total_amount_kopecks=0,
            sort_order=0,
        )
        session.add(line)
        await session.flush()
        session.add(
            BillingInvoiceV2Source(
                tenant_id=tenant_id,
                invoice_line_id=line.id,
                billing_ledger_entry_id=row.id,
                signed_amount_kopecks_snapshot=0,
            )
        )
        await session.commit()

    async with SessionLocal() as session:
        assert await charge_storage_day(session, tenant_id, day=day) == 1

    after = await _storage_entries(tenant_id)
    assert len(after) == 2, after
    # Выставленная строка осталась нетронутой, разница легла соседней.
    kinds = {entry.event_kind: entry.quantity for entry in after}
    assert kinds[f"storage_day:{day.isoformat()}"] == full / 2
    assert kinds[f"storage_day:{day.isoformat()}:topup1"] == full - full / 2
    assert sum(entry.quantity for entry in after) == full

    # Ещё один проход ничего не добавляет: за сутки уже начислено сколько надо.
    async with SessionLocal() as session:
        assert await charge_storage_day(session, tenant_id, day=day) == 0
    assert len(await _storage_entries(tenant_id)) == 2

    # The editable storage statement must show the same ledger total, including
    # the supplementary charge whose base entry is already attached to an invoice.
    from app.models.storage_measurement import StorageMeasurement
    from app.models.storage_statement import StorageStatement
    from app.services.storage_statement_service import get_storage_night_charges_batch

    statement = StorageStatement(
        id=uuid.uuid4(), tenant_id=tenant_id, seller_id=seller_id,
        warehouse_id=after[0].warehouse_id, period_start=day, period_end=day,
    )
    measurement = StorageMeasurement(product_id=_product_id)
    async with SessionLocal() as session:
        charges = await get_storage_night_charges_batch(
            session, tenant_id, [statement], {statement.id: [measurement]},
        )
    actual = charges[statement.id][_product_id]
    assert actual.liter_days == full
    amounts = [entry.amount for entry in after if entry.amount is not None]
    assert actual.amount_kopecks == (sum(amounts) if amounts else None)
