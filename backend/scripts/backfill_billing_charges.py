"""Разовое начисление задним числом по уже прошедшим операциям.

Зачем. Начисление пишется в момент события: провели приёмку — система нашла
ставку и записала строку с суммой. Если в тот момент ставки не было или биллинг
ещё не был включён, строка не появляется, и задним числом её никто не создаёт.
Отчёт с этим уже справляется — он считает цену по истории ставок сам, — но счёт
собирается именно из начислений, поэтому старые документы в счёт не попадают.

Скрипт проходит по операциям за период, находит те, у которых начисления нет, и
создаёт его по ставке, действовавшей **на дату операции**, а не по сегодняшней.

Безопасность:
  * по умолчанию — сухой прогон, ничего не пишется;
  * повторный запуск ничего не задваивает: начисление идемпотентно по документу;
  * операции, для которых ставки на их дату не найдено, не выдумываются, а
    попадают в отчёт скрипта отдельной строкой.

Запуск:
    python -m scripts.backfill_billing_charges --from 2026-08-01 --to 2026-08-31
    python -m scripts.backfill_billing_charges --from 2026-08-01 --to 2026-08-31 --apply
    # если у арендатора не проставлена дата начала биллинга:
    python -m scripts.backfill_billing_charges --from 2026-08-01 --to 2026-08-31 \
        --enable-billing-from 2026-08-01 --apply
"""

from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.operation_fact import OperationFact
from app.models.tenant import Tenant
from app.services.billing_ledger_service import (
    BillingLedgerError,
    _active_charge_for_source,
    record_operational_charge,
)

MOSCOW = ZoneInfo("Europe/Moscow")


def _interval(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    start = datetime.combine(date_from, time.min, tzinfo=MOSCOW)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=MOSCOW)
    return start, end


async def _facts(
    session: AsyncSession, *, start: datetime, end: datetime, tenant_id: str | None
) -> list[OperationFact]:
    query = (
        select(OperationFact)
        .where(
            OperationFact.occurred_at >= start,
            OperationFact.occurred_at < end,
            OperationFact.seller_id.is_not(None),
            OperationFact.billable_service_code.is_not(None),
            OperationFact.reversal_of_id.is_(None),
        )
        .order_by(OperationFact.occurred_at)
    )
    if tenant_id:
        query = query.where(OperationFact.tenant_id == tenant_id)
    return list((await session.scalars(query)).all())


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="date_from", required=True, help="дата начала, ГГГГ-ММ-ДД")
    parser.add_argument("--to", dest="date_to", required=True, help="дата конца, включительно")
    parser.add_argument("--tenant", dest="tenant_id", default=None, help="ограничить арендатором")
    parser.add_argument(
        "--enable-billing-from",
        dest="enable_from",
        default=None,
        help="проставить арендаторам дату начала биллинга, если она пустая",
    )
    parser.add_argument(
        "--apply", action="store_true", help="записать изменения (иначе сухой прогон)"
    )
    args = parser.parse_args()

    date_from = date.fromisoformat(args.date_from)
    date_to = date.fromisoformat(args.date_to)
    enable_from = date.fromisoformat(args.enable_from) if args.enable_from else None
    start, end = _interval(date_from, date_to)

    created = 0
    existed = 0
    unpriced: dict[str, int] = defaultdict(int)
    money = 0

    async with SessionLocal() as session:
        if enable_from is not None:
            tenants = list((await session.scalars(select(Tenant))).all())
            for tenant in tenants:
                if args.tenant_id and str(tenant.id) != args.tenant_id:
                    continue
                if tenant.billing_enabled_from is None:
                    print(f"арендатор {tenant.name}: дата начала биллинга → {enable_from}")
                    if args.apply:
                        tenant.billing_enabled_from = enable_from
            if args.apply:
                await session.flush()

        facts = await _facts(session, start=start, end=end, tenant_id=args.tenant_id)
        print(f"операций за период: {len(facts)}")

        for fact in facts:
            existing = await _active_charge_for_source(
                session,
                tenant_id=fact.tenant_id,
                source_type=fact.document_type,
                source_id=fact.document_id,
            )
            if existing is not None:
                existed += 1
                continue
            try:
                entry = await record_operational_charge(
                    session,
                    tenant_id=fact.tenant_id,
                    seller_id=fact.seller_id,
                    source_type=fact.document_type,
                    source_id=fact.document_id,
                    source=fact.source_kind,
                    service_code=str(fact.billable_service_code),
                    quantity=Decimal(int(fact.item_quantity or 0)),
                    occurred_at=fact.occurred_at,
                    performer_id=None,
                    warehouse_id=fact.warehouse_id,
                )
            except BillingLedgerError as exc:
                unpriced[f"ошибка: {exc}"] += 1
                continue
            if entry is None:
                # Дата начала биллинга у арендатора позже операции — начисление
                # сознательно не создаётся. Это не сбой, а настройка.
                unpriced["биллинг не включён на эту дату"] += 1
                continue
            if entry.amount is None:
                unpriced[f"нет ставки: {fact.billable_service_code}"] += 1
            else:
                money += int(entry.amount)
            created += 1

        if args.apply:
            await session.commit()
            print("изменения записаны")
        else:
            await session.rollback()
            print("сухой прогон: ничего не записано, повторите с --apply")

    print(f"начислений создано: {created}, уже было: {existed}, сумма: {money / 100:.2f} ₽")
    for reason, count in sorted(unpriced.items(), key=lambda row: -row[1]):
        print(f"  без суммы — {reason}: {count}")


if __name__ == "__main__":
    asyncio.run(main())
