"""Ежесуточное начисление за хранение.

Хранение — единственная услуга, которую нельзя привязать к событию: товар
просто лежит. Раньше деньги за него появлялись только после того, как человек
руками нажимал «Сформировать за месяц», а потом «Зафиксировать». Забыл нажать —
месяц хранения бесплатный, нажал дважды по разным складам в разное время —
копейка разъехалась.

Теперь каждую ночь в 00:00 по Москве система сама проходит по товарам, лежащим
на складе, считает литро-дни за прошедшие сутки и пишет начисление по ставке
этого товара: индивидуальная по товару перебивает ставку селлера, ставка
селлера — общую.

Начисление за сутки идемпотентно: повтор задачи за тот же день не создаёт
вторую строку. Уникальность держит сама база — пара «услуга + событие», где
событием служит связка склад/товар и дата суток.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.billing import BillingLedgerEntry
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.product_dimension_event import ProductDimensionEvent
from app.models.tenant import Tenant
from app.models.warehouse import Warehouse
from app.services.billing_ledger_service import (
    BillingLedgerError,
    _resolve_v2_tariff,
    postgres_integer,
    postgres_numeric,
)
from app.services.storage_measurement_service import (
    MOSCOW,
    StorageMeasurementError,
    interval_liter_days,
    rebuild_storage_measurements,
)

logger = logging.getLogger(__name__)

STORAGE_SERVICE_CODE = "storage"
STORAGE_UNIT = "liter_day"
SOURCE = "storage_daily"
SOURCE_TYPE = "storage_day"
# Пространство имён для устойчивого идентификатора события суток. Строка
# начисления адресуется складом, товаром и датой, поэтому повторный запуск
# задачи попадает в ту же самую запись, а не создаёт вторую.
SOURCE_NAMESPACE = uuid.UUID("6f3b6a2e-1f2c-4a6a-9d5f-2f2d1a7c40b1")


def _source_id(*, warehouse_id: uuid.UUID, product_id: uuid.UUID) -> uuid.UUID:
    return uuid.uuid5(SOURCE_NAMESPACE, f"{warehouse_id}:{product_id}")


def _event_kind(day: date) -> str:
    return f"storage_day:{day.isoformat()}"


def previous_moscow_day(now: datetime | None = None) -> date:
    """Прошедшие сутки для запуска в 00:00 по Москве."""
    moment = (now or datetime.now(MOSCOW)).astimezone(MOSCOW)
    return moment.date() - timedelta(days=1)


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, MOSCOW)
    return start, start + timedelta(days=1)


async def charge_storage_day(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    day: date,
) -> int:
    """Начислить хранение арендатора за одни сутки. Повтор безопасен.

    Возвращает количество созданных строк начисления.
    """
    billing_enabled_from = await session.scalar(
        select(Tenant.billing_enabled_from).where(Tenant.id == tenant_id)
    )
    if billing_enabled_from is None or day < billing_enabled_from:
        # Пока у арендатора не проставлена дата начала биллинга, работа склада
        # не стоит денег — так же, как и у операционных начислений.
        return 0

    start, end = _day_bounds(day)
    warehouse_ids = set(
        (
            await session.scalars(
                select(Warehouse.id).where(
                    Warehouse.tenant_id == tenant_id,
                    Warehouse.is_operational.is_(True),
                )
            )
        ).all()
    )
    if not warehouse_ids:
        return 0

    # Литро-дни считаются по всей истории движений до конца суток: остаток на
    # начало дня восстанавливается из неё, отдельного среза остатков нет.
    movements = list(
        (
            await session.scalars(
                select(InventoryMovement)
                .where(
                    InventoryMovement.tenant_id == tenant_id,
                    InventoryMovement.warehouse_id.in_(warehouse_ids),
                    InventoryMovement.created_at < end,
                )
                .order_by(InventoryMovement.created_at, InventoryMovement.id)
            )
        ).all()
    )
    if not movements:
        return 0

    product_ids = {movement.product_id for movement in movements}
    products = {
        product.id: product
        for product in (
            await session.scalars(select(Product).where(Product.id.in_(product_ids)))
        ).all()
    }
    events_by_product: dict[uuid.UUID, list[ProductDimensionEvent]] = {}
    for event in (
        await session.scalars(
            select(ProductDimensionEvent)
            .where(
                ProductDimensionEvent.tenant_id == tenant_id,
                ProductDimensionEvent.product_id.in_(product_ids),
            )
            .order_by(ProductDimensionEvent.observed_at, ProductDimensionEvent.id)
        )
    ).all():
        events_by_product.setdefault(event.product_id, []).append(event)

    grouped: dict[tuple[uuid.UUID, uuid.UUID, uuid.UUID], list[InventoryMovement]] = {}
    for movement in movements:
        if movement.seller_id is None or movement.warehouse_id is None:
            continue
        if movement.product_id not in products:
            continue
        grouped.setdefault(
            (movement.seller_id, movement.warehouse_id, movement.product_id), []
        ).append(movement)
    if not grouped:
        return 0

    already_charged = set(
        (
            await session.scalars(
                select(BillingLedgerEntry.source_id).where(
                    BillingLedgerEntry.tenant_id == tenant_id,
                    BillingLedgerEntry.service_code == STORAGE_SERVICE_CODE,
                    BillingLedgerEntry.source_type == SOURCE_TYPE,
                    BillingLedgerEntry.event_kind == _event_kind(day),
                )
            )
        ).all()
    )

    created = 0
    for (seller_id, warehouse_id, product_id), product_movements in grouped.items():
        source_id = _source_id(warehouse_id=warehouse_id, product_id=product_id)
        if source_id in already_charged:
            continue
        product = products[product_id]
        try:
            liter_days, missing_dimensions = interval_liter_days(
                product_movements,
                events_by_product.get(product_id, []),
                legacy_volume_liters=product.volume_liters,
                start=start,
                end=end,
            )
        except StorageMeasurementError:
            # Остаток, восстановленный по движениям, ушёл в минус — посчитать
            # хранение честно нельзя. Молча начислять ноль хуже, чем пропустить:
            # строки не будет, и дыра останется видимой.
            logger.warning(
                "storage day skipped, negative reconstructed stock: "
                "tenant=%s warehouse=%s product=%s day=%s",
                tenant_id,
                warehouse_id,
                product_id,
                day,
            )
            continue
        if liter_days <= 0:
            # Товара на складе в эти сутки не было либо у него нет обмера —
            # платить не за что. Строка с нулём только засорила бы счёт.
            continue
        if missing_dimensions:
            # Часть суток товар лежал без известного объёма. Оплачиваем то, что
            # посчитано; недостающий обмер оператор вносит на экране хранения,
            # и следующая ночь посчитает уже полностью.
            logger.info(
                "storage day partially measured: tenant=%s product=%s day=%s",
                tenant_id,
                product_id,
                day,
            )

        tariff = await _resolve_v2_tariff(
            session,
            tenant_id=tenant_id,
            seller_id=seller_id,
            product_id=product_id,
            service_code=STORAGE_SERVICE_CODE,
            occurred_at=end - timedelta(microseconds=1),
        )
        if tariff is not None and tariff.unit != STORAGE_UNIT:
            # Хранение меряется только литро-днями. Ставка в других единицах
            # означала бы, что литро-дни умножают на цену штуки.
            logger.warning(
                "storage tariff has wrong unit, day skipped: tenant=%s tariff=%s unit=%s",
                tenant_id,
                tariff.id,
                tariff.unit,
            )
            continue
        try:
            quantity = postgres_numeric(
                liter_days, precision=14, scale=4, field="billing_quantity"
            )
            amount = (
                None
                if tariff is None
                else postgres_integer(Decimal(tariff.rate) * quantity, field="billing_amount")
            )
        except BillingLedgerError:
            logger.exception(
                "storage day amount out of range: tenant=%s product=%s day=%s",
                tenant_id,
                product_id,
                day,
            )
            continue

        entry = BillingLedgerEntry(
            tenant_id=tenant_id,
            seller_id=seller_id,
            warehouse_id=warehouse_id,
            tariff_version_v2_id=tariff.id if tariff is not None else None,
            entry_type="charge",
            service_code=STORAGE_SERVICE_CODE,
            source=SOURCE,
            source_type=SOURCE_TYPE,
            source_id=source_id,
            event_kind=_event_kind(day),
            unit=STORAGE_UNIT,
            quantity=quantity,
            rate=tariff.rate if tariff is not None else None,
            amount=amount,
            # Начисление принадлежит тем суткам, за которые оно посчитано, а не
            # моменту запуска задачи: иначе хранение за 31-е попало бы в счёт
            # следующего месяца.
            occurred_at=(end - timedelta(microseconds=1)).astimezone(UTC),
        )
        nested = await session.begin_nested()
        try:
            session.add(entry)
            await session.flush()
        except IntegrityError:
            # Параллельный запуск уже записал эти сутки — это и есть нужный
            # результат, второй строки быть не должно.
            await nested.rollback()
        else:
            await nested.commit()
            created += 1
    await session.commit()
    return created


async def refresh_storage_drafts(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    day: date,
) -> None:
    """Пересобрать черновики расчёта хранения, которые смотрит оператор.

    Раньше их пересобирала кнопка «Сформировать за месяц». Кнопки больше нет,
    но экран хранения нужен: по нему вносят обмеры габаритов и печатают расчёт.
    Поэтому черновики обновляются той же ночью — за сутки, которые посчитали, и
    за текущий месяц, если это уже другой месяц.
    """
    months = {day.replace(day=1), datetime.now(MOSCOW).date().replace(day=1)}
    for period_start in sorted(months):
        await rebuild_storage_measurements(session, tenant_id, period_start=period_start)
    await session.commit()


# Сколько суток назад задача готова догонять пропуски. Хранение — деньги: если
# ночь не отработала (упал воркер, лежал сервер, выкатка затянулась), сутки
# нельзя терять молча. Ограничение нужно, чтобы первый запуск в новом
# окружении не начал считать всю историю склада.
CATCH_UP_DAYS = 14


async def missing_charge_days(
    session: AsyncSession, tenant_id: uuid.UUID, *, until: date, depth: int = CATCH_UP_DAYS
) -> list[date]:
    """Сутки за последние `depth` дней, по которым начислений так и не появилось."""
    first = until - timedelta(days=depth - 1)
    charged = set(
        (
            await session.scalars(
                select(BillingLedgerEntry.event_kind).where(
                    BillingLedgerEntry.tenant_id == tenant_id,
                    BillingLedgerEntry.service_code == STORAGE_SERVICE_CODE,
                    BillingLedgerEntry.source_type == SOURCE_TYPE,
                    BillingLedgerEntry.occurred_at >= _day_bounds(first)[0],
                )
            )
        ).all()
    )
    days: list[date] = []
    current = first
    while current <= until:
        if _event_kind(current) not in charged:
            days.append(current)
        current += timedelta(days=1)
    return days


async def run_daily_storage_charge_all_tenants(*, day: date | None = None) -> int:
    """Ночной проход по всем арендаторам. Сбой одного не отменяет остальных.

    Проход не ограничивается вчерашним днём: он добирает все сутки за две
    недели, по которым начислений нет. Иначе одна пропущенная ночь означала бы,
    что за те сутки не заплатят никогда — повторно их никто не посчитает.
    """
    charged_day = day or previous_moscow_day()
    async with SessionLocal() as session:
        tenant_ids = list((await session.scalars(select(Tenant.id))).all())
    total = 0
    for tenant_id in tenant_ids:
        # Деньги идут первыми и в своей транзакции: пересборка черновиков —
        # это витрина для оператора, и её падение не должно стоить начислений.
        async with SessionLocal() as session:
            try:
                pending = (
                    [charged_day]
                    if day is not None
                    else await missing_charge_days(session, tenant_id, until=charged_day)
                )
            except Exception:
                await session.rollback()
                logger.exception("storage catch-up scan failed: tenant=%s", tenant_id)
                pending = [charged_day]
        for pending_day in pending:
            async with SessionLocal() as session:
                try:
                    total += await charge_storage_day(session, tenant_id, day=pending_day)
                except Exception:
                    await session.rollback()
                    logger.exception(
                        "daily storage charge failed: tenant=%s day=%s", tenant_id, pending_day
                    )
        async with SessionLocal() as session:
            try:
                await refresh_storage_drafts(session, tenant_id, day=charged_day)
            except Exception:
                await session.rollback()
                logger.exception(
                    "storage draft refresh failed: tenant=%s day=%s", tenant_id, charged_day
                )
    return total
