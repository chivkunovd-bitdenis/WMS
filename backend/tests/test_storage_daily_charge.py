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

    async with SessionLocal() as session:
        pending_after = await missing_charge_days(session, tenant_id, until=yesterday)
    assert before not in pending_after
    assert yesterday in pending_after
