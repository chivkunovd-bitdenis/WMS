from __future__ import annotations

import inspect
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, cast
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, literal, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.billing import (
    BillingLedgerEntry,
    BillingLedgerLine,
    BillingRunIssue,
    BillingTariffVersion,
    BillingTariffVersionV2,
)
from app.models.tenant import Tenant

MOSCOW = ZoneInfo("Europe/Moscow")
POSTGRES_INTEGER_MIN = -(2**31)
POSTGRES_INTEGER_MAX = 2**31 - 1
# Упаковка считается по факту отгрузки товара — по тем же штукам, что и сама
# отгрузка. Ни события упаковки, ни кнопка «всё упаковано» на неё не влияют:
# оператор может не нажать кнопку, а коробка всё равно уехала упакованной.
PACKING_SERVICE_CODE = "packing"
OPERATIONAL_BILLING_ISSUE_REASON = "billing_calculation_overflow"
OPERATIONAL_BILLING_ISSUE_MESSAGE = (
    "Начисление не рассчитано: значение превышает допустимый предел. Складская операция завершена."
)


class BillingLedgerError(ValueError):
    """A billing fact cannot be represented without corrupting its source transaction."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class OperationalBillingLine:
    product_id: uuid.UUID | None
    quantity: Decimal
    source_snapshot: dict[str, object]
    operation_fact_line_id: uuid.UUID | None = None


def product_billing_lines(
    items: Iterable[tuple[uuid.UUID, Decimal, dict[str, object]]],
) -> list[OperationalBillingLine]:
    return [
        OperationalBillingLine(product_id=item[0], quantity=item[1], source_snapshot=item[2])
        for item in items
    ]


def postgres_numeric(value: Decimal, *, precision: int, scale: int, field: str) -> Decimal:
    """Validate and normalize a Decimal before a PostgreSQL NUMERIC write."""
    if precision <= 0 or scale < 0 or scale > precision or not value.is_finite():
        raise BillingLedgerError(f"{field}_overflow")
    quantum = Decimal(1).scaleb(-scale)
    maximum = (Decimal(10) ** (precision - scale)) - quantum
    try:
        normalized = value.quantize(quantum, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise BillingLedgerError(f"{field}_overflow") from exc
    if abs(normalized) > maximum:
        raise BillingLedgerError(f"{field}_overflow")
    return normalized


def postgres_integer(value: Decimal, *, field: str) -> int:
    if not value.is_finite():
        raise BillingLedgerError(f"{field}_overflow")
    try:
        rounded = int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, OverflowError, ValueError) as exc:
        raise BillingLedgerError(f"{field}_overflow") from exc
    if not POSTGRES_INTEGER_MIN <= rounded <= POSTGRES_INTEGER_MAX:
        raise BillingLedgerError(f"{field}_overflow")
    return rounded


async def record_operational_billing_issue(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID,
    occurred_at: datetime,
) -> BillingRunIssue:
    """Persist a visible billing issue without undoing the completed warehouse fact."""
    period_date = occurred_at.astimezone(MOSCOW).date()
    period = period_date.replace(day=1)
    issue_scope = (
        BillingRunIssue.tenant_id == tenant_id,
        BillingRunIssue.seller_id == seller_id,
        BillingRunIssue.period == period,
        BillingRunIssue.reason == OPERATIONAL_BILLING_ISSUE_REASON,
    )
    existing = await session.scalar(select(BillingRunIssue).where(*issue_scope))
    if existing is not None:
        return existing
    issue = BillingRunIssue(
        tenant_id=tenant_id,
        seller_id=seller_id,
        period=period,
        reason=OPERATIONAL_BILLING_ISSUE_REASON,
        message=OPERATIONAL_BILLING_ISSUE_MESSAGE,
    )
    savepoint = await session.begin_nested()
    try:
        session.add(issue)
        await session.flush()
    except IntegrityError:
        await savepoint.rollback()
        concurrent = await session.scalar(select(BillingRunIssue).where(*issue_scope))
        if concurrent is None:
            raise
        return concurrent
    else:
        await savepoint.commit()
        return issue


async def resolve_active_tariff(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID | None,
    warehouse_id: uuid.UUID | None,
    service_code: str,
    fact_date: date,
) -> BillingTariffVersion | None:
    """Resolve the most specific tariff while preserving explicit scope priority."""
    seller_scope = (
        BillingTariffVersion.seller_id.is_(None)
        if seller_id is None
        else (
            (BillingTariffVersion.seller_id == seller_id) | BillingTariffVersion.seller_id.is_(None)
        )
    )
    warehouse_scope = (
        BillingTariffVersion.warehouse_id.is_(None)
        if warehouse_id is None
        else (
            (BillingTariffVersion.warehouse_id == warehouse_id)
            | BillingTariffVersion.warehouse_id.is_(None)
        )
    )
    if warehouse_id is not None and seller_id is not None:
        specificity = case(
            (
                and_(
                    BillingTariffVersion.warehouse_id == warehouse_id,
                    BillingTariffVersion.seller_id == seller_id,
                ),
                0,
            ),
            (
                and_(
                    BillingTariffVersion.warehouse_id.is_(None),
                    BillingTariffVersion.seller_id == seller_id,
                ),
                1,
            ),
            (
                and_(
                    BillingTariffVersion.warehouse_id == warehouse_id,
                    BillingTariffVersion.seller_id.is_(None),
                ),
                2,
            ),
            else_=3,
        )
    elif warehouse_id is not None:
        specificity = case(
            (BillingTariffVersion.warehouse_id == warehouse_id, 0),
            else_=1,
        )
    elif seller_id is not None:
        specificity = case(
            (BillingTariffVersion.seller_id == seller_id, 0),
            else_=1,
        )
    else:
        specificity = case((BillingTariffVersion.id.is_not(None), 0), else_=1)

    return cast(
        BillingTariffVersion | None,
        await session.scalar(
            select(BillingTariffVersion)
            .where(
                BillingTariffVersion.tenant_id == tenant_id,
                BillingTariffVersion.service_code == service_code,
                BillingTariffVersion.valid_from <= fact_date,
                (
                    BillingTariffVersion.valid_to.is_(None)
                    | (BillingTariffVersion.valid_to >= fact_date)
                ),
                seller_scope,
                warehouse_scope,
            )
            .order_by(specificity, BillingTariffVersion.valid_from.desc())
        ),
    )


async def _active_charge_for_source(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    source_type: str,
    source_id: uuid.UUID,
    service_code: str | None = None,
) -> BillingLedgerEntry | None:
    """Return the only charge for a source that has not been reversed.

    Один документ теперь платный дважды: за саму операцию и за упаковку. База
    это и так разрешает — уникальность идёт по паре «услуга + событие», — а вот
    поиск существующего начисления без услуги нашёл бы чужую строку и молча
    отменил бы второе начисление. Поэтому услуга участвует в отборе.
    """
    charge = aliased(BillingLedgerEntry)
    reversal = aliased(BillingLedgerEntry)
    return cast(
        BillingLedgerEntry | None,
        await session.scalar(
            select(charge)
            .outerjoin(reversal, reversal.reversal_of_id == charge.id)
            .where(
                charge.tenant_id == tenant_id,
                charge.source_type == source_type,
                charge.source_id == source_id,
                charge.entry_type == "charge",
                reversal.id.is_(None),
                *(
                    ()
                    if service_code is None
                    else (charge.service_code == service_code,)
                ),
            )
            .order_by(charge.occurred_at.desc(), charge.id.desc())
        ),
    )


async def _latest_reversal_for_source(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    source_type: str,
    source_id: uuid.UUID,
    service_code: str | None = None,
) -> BillingLedgerEntry | None:
    """Return the latest immutable reversal in a source's charge history."""
    charge = aliased(BillingLedgerEntry)
    reversal = aliased(BillingLedgerEntry)
    return cast(
        BillingLedgerEntry | None,
        await session.scalar(
            select(reversal)
            .join(charge, reversal.reversal_of_id == charge.id)
            .where(
                charge.tenant_id == tenant_id,
                charge.source_type == source_type,
                charge.source_id == source_id,
                charge.entry_type == "charge",
                *(
                    ()
                    if service_code is None
                    else (charge.service_code == service_code,)
                ),
            )
            .order_by(reversal.occurred_at.desc(), reversal.id.desc())
        ),
    )


async def _resolve_v2_tariff(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID | None,
    product_id: uuid.UUID | None,
    service_code: str,
    occurred_at: datetime,
) -> BillingTariffVersionV2 | None:
    scope: list[Any] = [BillingTariffVersionV2.product_id.is_(None)]
    if product_id is not None:
        scope = [
            (BillingTariffVersionV2.product_id == product_id)
            | BillingTariffVersionV2.product_id.is_(None)
        ]
    seller_scope = (
        BillingTariffVersionV2.seller_id.is_(None)
        if seller_id is None
        else (
            (BillingTariffVersionV2.seller_id == seller_id)
            | BillingTariffVersionV2.seller_id.is_(None)
        )
    )
    # Приоритет: товар → селлер → общая; дата решает только внутри одного
    # уровня точности.
    #
    # Ветки собираются условно намеренно. SQLAlchemy превращает `col == None` в
    # `col IS NULL`, поэтому запись вида `product_id == product_id` при пустом
    # product_id давала высшую точность КАЖДОЙ нетоварной ставке — все они
    # оказывались равны, и побеждала просто самая свежая. Так общая ставка,
    # заведённая позже, перебивала индивидуальную ставку селлера.
    branches: list[Any] = []
    if product_id is not None:
        branches.append((BillingTariffVersionV2.product_id == product_id, 0))
    if seller_id is not None:
        branches.append(
            (
                BillingTariffVersionV2.seller_id == seller_id,
                1,
            )
        )
    specificity = case(*branches, else_=2) if branches else literal(2)
    return cast(
        BillingTariffVersionV2 | None,
        await session.scalar(
            select(BillingTariffVersionV2)
            .where(
                BillingTariffVersionV2.tenant_id == tenant_id,
                BillingTariffVersionV2.service_code == service_code,
                # Employee rates are a separate pay matrix; they never price a
                # seller operation just because their seller/product scope is null.
                BillingTariffVersionV2.employee_user_id.is_(None),
                BillingTariffVersionV2.enabled.is_(True),
                BillingTariffVersionV2.valid_from_at <= occurred_at,
                (
                    BillingTariffVersionV2.valid_to_at.is_(None)
                    | (BillingTariffVersionV2.valid_to_at > occurred_at)
                ),
                seller_scope,
                *scope,
            )
            .order_by(specificity, BillingTariffVersionV2.valid_from_at.desc())
        ),
    )


async def record_operational_charge(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    seller_id: uuid.UUID | None,
    source_type: str,
    source_id: uuid.UUID,
    source: str,
    service_code: str,
    quantity: Decimal,
    occurred_at: datetime,
    performer_id: uuid.UUID | None,
    warehouse_id: uuid.UUID | None = None,
    lines: list[OperationalBillingLine] | None = None,
) -> BillingLedgerEntry | None:
    """Record the first final operational fact, without blocking on a missing tariff."""
    fact_date = occurred_at.astimezone(MOSCOW).date()
    billing_enabled_from = await session.scalar(
        select(Tenant.billing_enabled_from).where(Tenant.id == tenant_id)
    )
    if billing_enabled_from is None or fact_date < billing_enabled_from:
        return None

    existing = await _active_charge_for_source(
        session,
        tenant_id=tenant_id,
        source_type=source_type,
        source_id=source_id,
        service_code=service_code,
    )
    if existing is not None:
        return existing

    previous_reversal = await _latest_reversal_for_source(
        session,
        tenant_id=tenant_id,
        source_type=source_type,
        source_id=source_id,
        service_code=service_code,
    )
    event_kind = (
        "completed"
        if previous_reversal is None
        else f"completed_after_reversal:{previous_reversal.id}"
    )

    tariff = await resolve_active_tariff(
        session,
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        service_code=service_code,
        fact_date=fact_date,
    )
    rate = tariff.amount if tariff is not None else None
    billed_quantity = postgres_numeric(
        Decimal("1") if tariff is not None and tariff.unit == "document" else quantity,
        precision=14,
        scale=4,
        field="billing_quantity",
    )
    amount = (
        None
        if rate is None
        else postgres_integer(Decimal(rate) * billed_quantity, field="billing_amount")
    )
    entry = BillingLedgerEntry(
        tenant_id=tenant_id,
        seller_id=seller_id,
        warehouse_id=warehouse_id,
        tariff_version_id=tariff.id if tariff is not None else None,
        performer_id=performer_id,
        entry_type="charge",
        service_code=service_code,
        source=source,
        source_type=source_type,
        source_id=source_id,
        event_kind=event_kind,
        unit=tariff.unit if tariff is not None else "item",
        quantity=billed_quantity,
        rate=rate,
        amount=amount,
        occurred_at=occurred_at,
    )
    if lines:
        line_models: list[BillingLedgerLine] = []
        amounts: list[int | None] = []
        rates: set[int | None] = set()
        v2_tariff_ids: set[uuid.UUID] = set()
        for line in lines:
            line_tariff = await _resolve_v2_tariff(
                session,
                tenant_id=tenant_id,
                seller_id=seller_id,
                product_id=line.product_id,
                service_code=service_code,
                occurred_at=occurred_at,
            )
            line_quantity = postgres_numeric(
                line.quantity, precision=14, scale=4, field="billing_quantity"
            )
            line_rate = line_tariff.rate if line_tariff is not None else rate
            line_amount = (
                None
                if line_rate is None
                else postgres_integer(
                    Decimal(line_rate)
                    * (
                        Decimal("1")
                        if (
                            line_tariff.unit
                            if line_tariff is not None
                            else (tariff.unit if tariff is not None else "item")
                        )
                        == "document"
                        else line_quantity
                    ),
                    field="billing_amount",
                )
            )
            line_models.append(
                BillingLedgerLine(
                    tenant_id=tenant_id,
                    product_id=line.product_id,
                    operation_fact_line_id=line.operation_fact_line_id,
                    product_snapshot=line.source_snapshot,
                    physical_quantity=line_quantity,
                    billing_quantity=Decimal("1")
                    if (
                        line_tariff.unit
                        if line_tariff is not None
                        else (tariff.unit if tariff is not None else "item")
                    )
                    == "document"
                    else line_quantity,
                    billing_unit=line_tariff.unit
                    if line_tariff is not None
                    else (tariff.unit if tariff is not None else "item"),
                    tariff_version_v2_id=line_tariff.id if line_tariff is not None else None,
                    tariff_snapshot={
                        "service_code": service_code,
                        "source": source,
                        "legacy_tariff_id": str(tariff.id) if tariff is not None else None,
                        "v2_tariff_id": str(line_tariff.id) if line_tariff is not None else None,
                        "scope": {
                            "seller_id": str(seller_id),
                            "product_id": str(line.product_id)
                            if line.product_id is not None
                            else None,
                            "unit": line_tariff.unit
                            if line_tariff is not None
                            else (tariff.unit if tariff is not None else "item"),
                        },
                    },
                    rate=line_rate,
                    amount=line_amount,
                )
            )
            amounts.append(line_amount)
            rates.add(line_rate)
            if line_tariff is not None:
                v2_tariff_ids.add(line_tariff.id)
        entry.lines = line_models
        # Parent keeps a convenient V2 pointer only when every product line used
        # the same version.  The immutable per-line pointer/snapshot remains the
        # source of truth for mixed product overrides.
        if len(v2_tariff_ids) == 1:
            entry.tariff_version_v2_id = next(iter(v2_tariff_ids))
        if all(value is not None for value in amounts):
            entry.amount = sum(cast(int, value) for value in amounts)
            entry.rate = next(iter(rates)) if len(rates) == 1 else None
        else:
            entry.amount = None
            entry.rate = None
    # The unique source-event constraint is the concurrency guard.  Flush in a
    # savepoint so a concurrent finalisation can safely turn its constraint
    # error into the already committed ledger row without aborting the caller's
    # warehouse transaction.
    nested = await session.begin_nested()
    try:
        session.add(entry)
        await session.flush()
    except IntegrityError:
        await nested.rollback()
        concurrent = await _active_charge_for_source(
            session,
            tenant_id=tenant_id,
            source_type=source_type,
            source_id=source_id,
            service_code=service_code,
        )
        if concurrent is None:
            raise
        return concurrent
    else:
        await nested.commit()
        return entry


async def record_operational_reversal(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    source_type: str,
    source_id: uuid.UUID,
    occurred_at: datetime,
    performer_id: uuid.UUID | None,
    service_code: str | None = None,
) -> BillingLedgerEntry | None:
    """Reverse a recorded final fact once, preserving its immutable tariff snapshot.

    ``service_code`` называют, когда у документа несколько начислений — отгрузка
    и упаковка. Без него отменилась бы только одна строка из двух, и селлер
    остался бы должен за упаковку отменённой отгрузки.
    """
    original = await _active_charge_for_source(
        session,
        tenant_id=tenant_id,
        source_type=source_type,
        source_id=source_id,
        service_code=service_code,
    )
    if original is None:
        # Billing may have been disabled when the warehouse fact was recorded.
        # A repeated cancellation returns the historical reversal, without
        # creating a second correction.
        return await _latest_reversal_for_source(
            session,
            tenant_id=tenant_id,
            source_type=source_type,
            source_id=source_id,
            service_code=service_code,
        )

    existing = await session.scalar(
        select(BillingLedgerEntry).where(
            BillingLedgerEntry.reversal_of_id == original.id,
        )
    )
    if existing is not None:
        return existing

    reversal = BillingLedgerEntry(
        tenant_id=original.tenant_id,
        seller_id=original.seller_id,
        warehouse_id=original.warehouse_id,
        tariff_version_id=original.tariff_version_id,
        tariff_version_v2_id=original.tariff_version_v2_id,
        reversal_of_id=original.id,
        performer_id=performer_id,
        entry_type="reversal",
        service_code=original.service_code,
        source=original.source,
        source_type="billing_reversal",
        source_id=original.id,
        event_kind=f"reversal:{original.id}",
        unit=original.unit,
        quantity=-original.quantity,
        rate=original.rate,
        amount=-original.amount if original.amount is not None else None,
        occurred_at=occurred_at,
    )
    line_result = await session.scalars(
        select(BillingLedgerLine).where(BillingLedgerLine.ledger_entry_id == original.id)
    )
    # Lightweight unit-session doubles intentionally do not model child rows.
    original_lines = [] if inspect.iscoroutinefunction(line_result.all) else line_result.all()
    reversal.lines = [
        BillingLedgerLine(
            tenant_id=line.tenant_id,
            operation_fact_line_id=line.operation_fact_line_id,
            product_id=line.product_id,
            product_snapshot=line.product_snapshot,
            physical_quantity=-line.physical_quantity,
            billing_quantity=-line.billing_quantity,
            billing_unit=line.billing_unit,
            tariff_version_v2_id=line.tariff_version_v2_id,
            tariff_snapshot=line.tariff_snapshot,
            rate=line.rate,
            amount=-line.amount if line.amount is not None else None,
        )
        for line in original_lines
    ]
    nested = await session.begin_nested()
    try:
        session.add(reversal)
        await session.flush()
    except IntegrityError:
        await nested.rollback()
        concurrent = await session.scalar(
            select(BillingLedgerEntry).where(
                BillingLedgerEntry.reversal_of_id == original.id,
            )
        )
        if concurrent is None:
            raise
        return concurrent
    else:
        await nested.commit()
        return reversal
