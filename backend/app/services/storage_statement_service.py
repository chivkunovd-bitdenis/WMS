from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import (
    ROUND_HALF_UP,
    Decimal,
    InvalidOperation,
)
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.billing import BillingLedgerEntry, BillingTariffVersionV2
from app.models.storage_measurement import StorageMeasurement
from app.models.storage_statement import StorageStatement
from app.services.billing_ledger_service import (
    BillingLedgerError,
    postgres_integer,
    postgres_numeric,
)
from app.services.billing_tariff_matrix_service import (
    BillingTariffMatrixError,
    TariffVersionDraft,
    get_tariff_matrix,
    save_tariff_matrix,
)
from app.services.staff_packaging_billing_service import rub_to_kopecks
from app.services.storage_daily_charge_service import (
    SOURCE_TYPE as STORAGE_DAY_SOURCE_TYPE,
)
from app.services.storage_daily_charge_service import (
    STORAGE_SERVICE_CODE,
    storage_day_event_kind,
    storage_day_source_id,
)
from app.services.storage_measurement_service import MOSCOW


class StorageStatementError(ValueError):
    pass


STORAGE_TARIFF_MONEY_QUANTUM = Decimal("0.01")


def normalize_storage_tariff_amount(amount: Decimal) -> Decimal:
    """Round a storage rate to persisted money precision and reject zero."""
    try:
        normalized = amount.quantize(
            STORAGE_TARIFF_MONEY_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
        postgres_integer(normalized * Decimal(100), field="tariff_amount")
    except (InvalidOperation, BillingLedgerError) as exc:
        raise StorageStatementError("tariff_amount_out_of_range") from exc
    if normalized <= 0:
        raise StorageStatementError("tariff_amount_must_be_positive")
    return normalized


def normalize_storage_ledger_quantity(quantity: Decimal) -> Decimal:
    """Fit one storage charge quantity into billing ledger NUMERIC(14, 4)."""
    try:
        normalized = postgres_numeric(
            quantity,
            precision=14,
            scale=4,
            field="ledger_quantity",
        )
    except BillingLedgerError as exc:
        raise StorageStatementError("ledger_quantity_out_of_range") from exc
    if normalized < 0:
        raise StorageStatementError("ledger_quantity_out_of_range")
    return normalized


@dataclass(frozen=True)
class StorageNightCharge:
    """Итог ночных начислений по одному товару за период расчёта.

    ``amount_kopecks`` пуст, когда ни за одни сутки ставки не было: платить не за
    что, но литро-дни посчитаны, и показать их надо. Ноль здесь означал бы
    «бесплатно», а это другое утверждение.
    """

    liter_days: Decimal
    amount_kopecks: int | None


def _statement_source_ids(
    statement: StorageStatement, measurements: list[StorageMeasurement]
) -> set[uuid.UUID]:
    """Return the ledger source ids that unambiguously belong to a statement.

    A non-empty statement is published one measurement at a time.  A zero
    statement has no measurement id, so its own id is the single source event.
    This keeps the shared ledger's source-id uniqueness useful without a
    storage-specific charge table or a nullable, ambiguous source id.
    """
    return {row.id for row in measurements} or {statement.id}


def _storage_day_event_kinds(period_start: date, period_end: date) -> set[str]:
    """Ключи всех суток периода: по ним отбираются ночные начисления месяца."""
    kinds: set[str] = set()
    current = period_start
    while current <= period_end:
        kinds.add(storage_day_event_kind(current))
        current += timedelta(days=1)
    return kinds


async def get_storage_night_charges_batch(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    statements: Sequence[StorageStatement],
    rows_by_statement: dict[uuid.UUID, list[StorageMeasurement]],
) -> dict[uuid.UUID, dict[uuid.UUID, StorageNightCharge]]:
    """Ночные начисления за хранение, свёрнутые по товару за период расчёта.

    Экран хранения не считает деньги сам. Хранение начисляет ночная задача — по
    строке на пару «склад + товар» за каждые сутки, — и экран показывает ровно
    её результат. Пока экран считал по-своему, об одних и тех же сутках было две
    правды: одна на экране, другая в счёте, и какая настоящая, выяснить было
    нельзя.

    Один запрос на весь список: количество обращений к базе не должно расти по
    строке ведомости.
    """
    charges: dict[uuid.UUID, dict[uuid.UUID, StorageNightCharge]] = {
        statement.id: {} for statement in statements
    }
    # Строка начисления адресуется устойчивым идентификатором «склад + товар»,
    # поэтому обратный путь от проводки к товару строится из видимых строк.
    owners: dict[
        tuple[uuid.UUID | None, uuid.UUID | None, uuid.UUID],
        tuple[uuid.UUID, uuid.UUID],
    ] = {}
    kinds_by_statement: dict[uuid.UUID, set[str]] = {}
    all_kinds: set[str] = set()
    source_ids: set[uuid.UUID] = set()
    for statement in statements:
        kinds = _storage_day_event_kinds(statement.period_start, statement.period_end)
        kinds_by_statement[statement.id] = kinds
        all_kinds |= kinds
        for row in rows_by_statement.get(statement.id, []):
            source_id = storage_day_source_id(
                warehouse_id=statement.warehouse_id,
                product_id=row.product_id,
            )
            owners[(statement.seller_id, statement.warehouse_id, source_id)] = (
                statement.id,
                row.product_id,
            )
            source_ids.add(source_id)
    if not source_ids or not all_kinds:
        return charges

    entries = list(
        (
            await session.scalars(
                select(BillingLedgerEntry).where(
                    BillingLedgerEntry.tenant_id == tenant_id,
                    BillingLedgerEntry.service_code == STORAGE_SERVICE_CODE,
                    BillingLedgerEntry.source_type == STORAGE_DAY_SOURCE_TYPE,
                    BillingLedgerEntry.entry_type == "charge",
                    BillingLedgerEntry.source_id.in_(source_ids),
                    BillingLedgerEntry.event_kind.in_(all_kinds),
                )
            )
        ).all()
    )
    for entry in entries:
        owner = owners.get((entry.seller_id, entry.warehouse_id, entry.source_id))
        if owner is None:
            continue
        statement_id, product_id = owner
        if entry.event_kind not in kinds_by_statement[statement_id]:
            continue
        current = charges[statement_id].get(product_id)
        liter_days = (current.liter_days if current is not None else Decimal(0)) + Decimal(
            entry.quantity
        )
        amount = current.amount_kopecks if current is not None else None
        if entry.amount is not None:
            amount = (amount or 0) + int(entry.amount)
        charges[statement_id][product_id] = StorageNightCharge(
            liter_days=liter_days,
            amount_kopecks=amount,
        )
    return charges


async def get_storage_statement_for_print(
    session: AsyncSession, tenant_id: uuid.UUID, statement_id: uuid.UUID
) -> tuple[StorageStatement, list[StorageMeasurement]]:
    """Расчёт хранения для просмотра и печати — в любом состоянии документа.

    Раньше печать требовала зафиксированного документа: пока человек не нажал
    «Зафиксировать», распечатать было нечего. Фиксации больше нет — деньги
    пишет ночная задача, — поэтому печатаем текущий расчёт. У документов,
    зафиксированных до перехода, строки по-прежнему восстанавливаются из
    проводок: напечатанное однажды не должно поменяться задним числом.
    """
    statement = await session.scalar(
        select(StorageStatement)
        .options(joinedload(StorageStatement.seller), joinedload(StorageStatement.warehouse))
        .where(
            StorageStatement.id == statement_id,
            StorageStatement.tenant_id == tenant_id,
        )
    )
    if statement is None:
        raise StorageStatementError("not_found")
    # Reconstruct only this document's source measurements.  A seller may have
    # several months, so a broad seller ledger query is incorrect.
    measurements = list(
        (
            await session.scalars(
                select(StorageMeasurement)
                .where(StorageMeasurement.tenant_id == tenant_id)
                .where(StorageMeasurement.seller_id == statement.seller_id)
                .where(StorageMeasurement.warehouse_id == statement.warehouse_id)
                .where(StorageMeasurement.period_start == statement.period_start)
                .where(StorageMeasurement.period_end == statement.period_end)
                .options(
                    joinedload(StorageMeasurement.product),
                    joinedload(StorageMeasurement.dimension_event),
                )
                .order_by(StorageMeasurement.id)
            )
        ).all()
    )
    if statement.status != "fixed":
        return statement, measurements
    source_ids = _statement_source_ids(statement, measurements)
    ledger_rows = list(
        (
            await session.scalars(
                select(BillingLedgerEntry)
                .where(
                    BillingLedgerEntry.tenant_id == tenant_id,
                    BillingLedgerEntry.seller_id == statement.seller_id,
                    BillingLedgerEntry.source_type == "storage_measurement",
                    BillingLedgerEntry.service_code.in_(("storage", "storage_liter_day")),
                    BillingLedgerEntry.source_id.in_(source_ids),
                )
                .order_by(BillingLedgerEntry.id)
            )
        ).all()
    )
    by_id = {row.id: row for row in measurements}
    return statement, [by_id[row.source_id] for row in ledger_rows if row.source_id in by_id]



async def create_storage_tariff(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    amount: Decimal,
    valid_from: date,
    revision: int,
    seller_exception: tuple[uuid.UUID, Decimal, date] | None = None,
) -> tuple[BillingTariffVersionV2, BillingTariffVersionV2 | None, int]:
    """Сохранить общую и индивидуальную ставки хранения одной транзакцией.

    Прошлые расчёты новая ставка не переписывает. Хранение начисляет ночь по
    ставке, действовавшей в те сутки, и это факт, а не черновик: пересчитать его
    задним числом значило бы менять уже выставленные деньги.
    """
    amount = normalize_storage_tariff_amount(amount)
    if seller_exception is not None:
        seller_exception = (
            seller_exception[0],
            normalize_storage_tariff_amount(seller_exception[1]),
            seller_exception[2],
        )

    today_moscow = datetime.now(MOSCOW).date()
    effective_dates = [valid_from]
    if seller_exception is not None:
        effective_dates.append(seller_exception[2])
    if any(effective_date < today_moscow for effective_date in effective_dates):
        raise StorageStatementError("tariff_valid_from_in_past")

    config = await get_tariff_matrix(session, tenant_id=tenant_id)
    versions: list[TariffVersionDraft] = [
        {
            "seller_id": None,
            "product_id": None,
            "employee_user_id": None,
            "service_code": "storage",
            "unit": "liter_day",
            "enabled": True,
            "rate": rub_to_kopecks(amount),
            "valid_from_at": datetime.combine(valid_from, time.min, MOSCOW),
            "valid_to_at": None,
        }
    ]
    if seller_exception is not None:
        seller_id, seller_amount, seller_valid_from = seller_exception
        versions.append(
            {
                "seller_id": seller_id,
                "product_id": None,
                "employee_user_id": None,
                "service_code": "storage",
                "unit": "liter_day",
                "enabled": True,
                "rate": rub_to_kopecks(seller_amount),
                "valid_from_at": datetime.combine(seller_valid_from, time.min, MOSCOW),
                "valid_to_at": None,
            }
        )
    try:
        services = {
            state.service_code: state.enabled or state.service_code == "storage"
            for state in config.service_states
        }
        config = await save_tariff_matrix(
            session,
            tenant_id=tenant_id,
            revision=revision,
            services=services,
            versions=versions,
        )
        await session.flush()

        async def saved_version(draft: TariffVersionDraft) -> BillingTariffVersionV2:
            query = select(BillingTariffVersionV2).where(
                BillingTariffVersionV2.tenant_id == tenant_id,
                BillingTariffVersionV2.service_code == draft["service_code"],
                BillingTariffVersionV2.unit == draft["unit"],
                BillingTariffVersionV2.enabled == draft["enabled"],
                BillingTariffVersionV2.rate == draft["rate"],
                BillingTariffVersionV2.product_id.is_(None),
                BillingTariffVersionV2.employee_user_id.is_(None),
                BillingTariffVersionV2.valid_from_at
                == draft["valid_from_at"].astimezone(UTC),
            )
            if draft["seller_id"] is None:
                query = query.where(BillingTariffVersionV2.seller_id.is_(None))
            else:
                query = query.where(
                    BillingTariffVersionV2.seller_id == draft["seller_id"]
                )
            row = await session.scalar(query)
            if row is None:
                raise StorageStatementError("saved_tariff_not_found")
            return row

        common_tariff = await saved_version(versions[0])
        seller_tariff = (
            await saved_version(versions[1]) if seller_exception is not None else None
        )
        await session.commit()
    except (IntegrityError, BillingTariffMatrixError) as exc:
        await session.rollback()
        raise StorageStatementError(str(exc)) from exc
    except Exception:
        await session.rollback()
        raise

    await session.refresh(common_tariff)
    if seller_tariff is not None:
        await session.refresh(seller_tariff)

    return common_tariff, seller_tariff, config.revision


async def get_storage_ledger_rows(
    session: AsyncSession, tenant_id: uuid.UUID, statement_id: uuid.UUID
) -> list[Any]:
    """Return the immutable ledger snapshot belonging to one fixed statement."""
    statement = await session.scalar(
        select(StorageStatement).where(
            StorageStatement.id == statement_id,
            StorageStatement.tenant_id == tenant_id,
            StorageStatement.status == "fixed",
        )
    )
    if statement is None:
        raise StorageStatementError("not_found")
    measurements = list(
        (
            await session.scalars(
                select(StorageMeasurement.id).where(
                    StorageMeasurement.tenant_id == tenant_id,
                    StorageMeasurement.seller_id == statement.seller_id,
                    StorageMeasurement.warehouse_id == statement.warehouse_id,
                    StorageMeasurement.period_start == statement.period_start,
                    StorageMeasurement.period_end == statement.period_end,
                )
            )
        ).all()
    )
    return list(
        (
            await session.scalars(
                select(BillingLedgerEntry)
                .where(
                    BillingLedgerEntry.tenant_id == tenant_id,
                    BillingLedgerEntry.seller_id == statement.seller_id,
                    BillingLedgerEntry.source_type == "storage_measurement",
                    BillingLedgerEntry.service_code.in_(("storage", "storage_liter_day")),
                    BillingLedgerEntry.source_id.in_(set(measurements) or {statement.id}),
                )
                .order_by(BillingLedgerEntry.id)
            )
        ).all()
    )


async def get_storage_ledger_rows_batch(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    statements: Sequence[StorageStatement],
    rows_by_statement: dict[uuid.UUID, list[StorageMeasurement]],
) -> dict[uuid.UUID, list[BillingLedgerEntry]]:
    """Загрузить проводки списка ведомостей одним запросом."""
    source_to_statement: dict[uuid.UUID, uuid.UUID] = {}
    for statement in statements:
        rows = rows_by_statement.get(statement.id, [])
        for source_id in _statement_source_ids(statement, rows):
            source_to_statement[source_id] = statement.id
    if not source_to_statement:
        return {}

    ledger_rows = list(
        (
            await session.scalars(
                select(BillingLedgerEntry)
                .where(
                    BillingLedgerEntry.tenant_id == tenant_id,
                    BillingLedgerEntry.source_type == "storage_measurement",
                    BillingLedgerEntry.service_code.in_(("storage", "storage_liter_day")),
                    BillingLedgerEntry.source_id.in_(source_to_statement),
                )
                .order_by(BillingLedgerEntry.id)
            )
        ).all()
    )
    result: dict[uuid.UUID, list[BillingLedgerEntry]] = {
        statement.id: [] for statement in statements
    }
    for ledger_row in ledger_rows:
        statement_id = source_to_statement.get(ledger_row.source_id)
        if statement_id is not None:
            result[statement_id].append(ledger_row)
    return result
