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
from app.models.operation_fact import OperationFact, OperationFactLine
from app.models.tenant import Tenant
from app.services.billing_ledger_service import (
    PACKING_SERVICE_CODE,
    BillingLedgerError,
    _active_charge_for_source,
    product_billing_lines,
    record_operational_charge,
)

MOSCOW = ZoneInfo("Europe/Moscow")

# Начисляем только то, что живой код начисляет сам. У упаковки и подбора FBS
# факт пишется на каждое событие, а документ у них общий: одно начисление
# закрыло бы весь документ и оплатило его по первому событию. Такие услуги
# трогать нельзя — они попадут в отчёт скрипта отдельной строкой.
CHARGEABLE_SERVICES = frozenset({"inbound", "marketplace_outbound", "return", "fbs_order"})

# Упаковка своего факта не пишет: живой код начисляет её по тому же документу,
# что и отгрузку или заказ FBS, — уехавшая коробка упакована независимо от того,
# нажал ли оператор «всё упаковано». Задним числом её надо начислять так же,
# иначе ретроспективный счёт выйдет без половины услуги.
COMPANION_SERVICES: dict[str, tuple[str, ...]] = {
    "marketplace_outbound": (PACKING_SERVICE_CODE,),
    "fbs_order": (PACKING_SERVICE_CODE,),
}


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
            if not args.tenant_id:
                # Без явного арендатора один флаг включил бы биллинг задним
                # числом всем, у кого он сознательно выключен.
                raise SystemExit("--enable-billing-from требует --tenant")
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
            service = str(fact.billable_service_code)
            if service not in CHARGEABLE_SERVICES:
                unpriced[f"услуга начисляется не по документу: {service}"] += 1
                continue
            lines = list(
                (
                    await session.scalars(
                        select(OperationFactLine).where(
                            OperationFactLine.operation_fact_id == fact.id
                        )
                    )
                ).all()
            )
            for charged_service in (service, *COMPANION_SERVICES.get(service, ())):
                existing = await _active_charge_for_source(
                    session,
                    tenant_id=fact.tenant_id,
                    source_type=fact.document_type,
                    source_id=fact.document_id,
                    # У одного документа бывает несколько начислений: сама
                    # операция и упаковка по ней. Без услуги в отборе скрипт
                    # нашёл бы чужую строку и решил, что документ уже оплачен.
                    service_code=charged_service,
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
                        service_code=charged_service,
                        quantity=Decimal(int(fact.item_quantity or 0)),
                        occurred_at=fact.occurred_at,
                        performer_id=None,
                        warehouse_id=fact.warehouse_id,
                        # Без строк ставка ищется только в старой таблице
                        # тарифов, а матрица пишет в новую: начисление вышло бы
                        # с пустой суммой, и повторный, уже правильный, прогон
                        # стал бы невозможен.
                        lines=product_billing_lines(
                            (
                                line.product_id,
                                Decimal(int(line.item_quantity)),
                                {"fact": str(fact.id)},
                            )
                            for line in lines
                            if line.product_id is not None
                        ),
                    )
                except BillingLedgerError as exc:
                    unpriced[f"ошибка: {exc}"] += 1
                    continue
                if entry is None:
                    # Дата начала биллинга у арендатора позже операции —
                    # начисление сознательно не создаётся. Это настройка, а не сбой.
                    unpriced["биллинг не включён на эту дату"] += 1
                    continue
                if entry.amount is None:
                    unpriced[f"нет ставки: {charged_service}"] += 1
                else:
                    money += int(entry.amount)
                created += 1
                if args.apply and created % 200 == 0:
                    # Длинная транзакция на боевой базе держит блокировки и
                    # копит вложенные подтранзакции. Пишем порциями.
                    await session.commit()

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
