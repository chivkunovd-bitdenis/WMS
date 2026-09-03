"""Достроить недостающие факты по подтверждённым заказам FBS и поправить их даты.

Зачем. Тарификация сборки заказов FBS появилась 02.09.2026, и с этого момента
факт операции пишется в тот миг, когда опрос статусов увидел подтверждение WB.
Отсюда две беды на боевой базе:

  * **Заказы до выкатки фактов не получили вовсе.** У «Империи ФФ» из 5062
    подтверждённых заказов факт есть у 1574. Работа сделана, а платить за неё
    не с чего: и отчёт, и счёт собираются из фактов и начислений.
  * **У тех, что получили, дата — момент обработки.** Все 1577 записей стоят
    одним числом. Начислить по ним как есть значит уронить плату за две недели
    в один день и в один тариф.

Скрипт лечит обе. Он ничего не считает в деньгах: факт — это летопись работы,
а не сумма. Деньги отдельным шагом пишет `backfill_billing_charges.py`, уже
после того как в системе появятся тарифы, — и берёт ставку на дату операции.

Порядок работ на боевой базе:

    1. python -m scripts.backfill_fbs_order_facts --tenant <id>            # сухой прогон
    2. python -m scripts.backfill_fbs_order_facts --tenant <id> --apply    # факты и даты
    3. владелец заводит тарифы и дату начала биллинга
    4. python -m scripts.backfill_billing_charges --from … --to … --tenant <id> --apply

Дата работы берётся из самого заказа: когда упаковали, иначе когда подобрали,
иначе когда заказ появился у маркетплейса. Первые два — это и есть работа
склада; третий заполнен всегда и отличается от неё на день-два.

Безопасность:
  * по умолчанию — сухой прогон, ничего не пишется;
  * повторный запуск не задваивает: факт идемпотентен по ключу `fbs-order:<id>`;
  * складских таблиц скрипт не касается вовсе — только летопись операций;
  * дата правится только у фактов заказов FBS и только если она расходится с
    датой работы больше чем на сутки: у нормально записанных фактов расхождение
    в минуты, и трогать их незачем.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from collections import defaultdict
from datetime import UTC, date, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal
from app.models.fbs_order import FbsOrder, FbsOrderProduct
from app.models.operation_fact import OperationFact
from app.models.product import Product
from app.models.seller import Seller
from app.models.tenant import Tenant
from app.services.fbs_order_billing_service import (
    CONFIRMED_STATUSES,
    FBS_ORDER_SERVICE_CODE,
    SOURCE_TYPE,
    order_work_moment,
)
from app.services.operation_fact_service import OperationFactError, line_input, write_operation_fact

MOSCOW = ZoneInfo("Europe/Moscow")
# Насколько дата факта может отличаться от даты работы, чтобы считаться верной.
# Нормальный путь пишет факт в тот же миг; расхождение в сутки и больше значит,
# что факт проставлен моментом обработки, а не работой.
DATE_DRIFT_TOLERANCE = timedelta(days=1)
BATCH = 200


async def _positions(session: AsyncSession, order: FbsOrder) -> list[tuple[uuid.UUID | None, int]]:
    rows = (
        await session.execute(
            select(FbsOrderProduct.product_id, FbsOrderProduct.quantity).where(
                FbsOrderProduct.order_id == order.id
            )
        )
    ).all()
    if rows:
        return [(row[0], int(row[1])) for row in rows]
    return [(order.product_id, 1)]


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", dest="tenant_id", required=True, help="арендатор, обязателен")
    parser.add_argument(
        "--from", dest="date_from", default=None,
        help="не трогать заказы, работа по которым старше этой даты, ГГГГ-ММ-ДД",
    )
    parser.add_argument(
        "--apply", action="store_true", help="записать изменения (иначе сухой прогон)"
    )
    parser.add_argument(
        "--skip-dates", action="store_true",
        help="не трогать даты у уже записанных фактов, только достроить недостающие",
    )
    args = parser.parse_args()

    tenant_id = uuid.UUID(args.tenant_id)
    since = date.fromisoformat(args.date_from) if args.date_from else None

    created = 0
    skipped_no_seller = 0
    skipped_early = 0
    failed = 0
    redated = 0
    by_day: dict[date, int] = defaultdict(int)

    async with SessionLocal() as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None:
            raise SystemExit(f"арендатор {tenant_id} не найден")
        print(f"арендатор: {tenant.name}")

        orders = list(
            (
                await session.scalars(
                    select(FbsOrder)
                    .where(
                        FbsOrder.tenant_id == tenant_id,
                        FbsOrder.status.in_(tuple(CONFIRMED_STATUSES)),
                    )
                    .order_by(FbsOrder.created_at_wb)
                )
            ).all()
        )
        print(f"подтверждённых заказов: {len(orders)}")

        existing = {
            row[0]: (row[1], row[2])
            for row in (
                await session.execute(
                    select(OperationFact.document_id, OperationFact.id, OperationFact.occurred_at)
                    .where(
                        OperationFact.tenant_id == tenant_id,
                        OperationFact.document_type == SOURCE_TYPE,
                    )
                )
            ).all()
        }
        print(f"из них с фактом: {len(existing)}")

        seller_names = {
            row[0]: row[1]
            for row in (
                await session.execute(
                    select(Seller.id, Seller.name).where(Seller.tenant_id == tenant_id)
                )
            ).all()
        }
        product_ids = {order.product_id for order in orders if order.product_id is not None}
        products: dict[uuid.UUID, Product] = {}
        if product_ids:
            products = {
                product.id: product
                for product in (
                    await session.scalars(select(Product).where(Product.id.in_(product_ids)))
                ).all()
            }

        pending = 0
        for order in orders:
            moment = order_work_moment(order)
            work_day = moment.astimezone(MOSCOW).date()
            if since is not None and work_day < since:
                skipped_early += 1
                continue

            found = existing.get(order.id)
            if found is not None:
                if args.skip_dates:
                    continue
                fact_id, occurred_at = found
                stored = occurred_at if occurred_at.tzinfo else occurred_at.replace(tzinfo=UTC)
                if abs(stored - moment) <= DATE_DRIFT_TOLERANCE:
                    continue
                redated += 1
                by_day[work_day] += 1
                if args.apply:
                    fact = await session.get(OperationFact, fact_id)
                    if fact is not None:
                        fact.occurred_at = moment
                        pending += 1
                continue

            if order.seller_id is None:
                skipped_no_seller += 1
                continue

            positions = await _positions(session, order)
            quantity = sum(count for _, count in positions)
            by_day[work_day] += 1
            created += 1
            if not args.apply:
                continue
            try:
                await write_operation_fact(
                    session,
                    tenant_id=tenant_id,
                    operation_code="fbs_order",
                    billable_service_code=FBS_ORDER_SERVICE_CODE,
                    source_kind=SOURCE_TYPE,
                    source_event_id=order.id,
                    idempotency_key=f"fbs-order:{order.id}",
                    seller_id=order.seller_id,
                    seller_name_snapshot=seller_names.get(order.seller_id),
                    warehouse_id=order.warehouse_id,
                    marketplace=order.marketplace,
                    document_type=SOURCE_TYPE,
                    document_id=order.id,
                    document_number_snapshot=str(order.wb_order_id),
                    occurred_at=moment,
                    item_quantity=quantity,
                    lines=[
                        line_input(
                            products.get(product_id) if product_id else None, product_id, count
                        )
                        for product_id, count in positions
                    ],
                )
            except OperationFactError as exc:
                failed += 1
                created -= 1
                by_day[work_day] -= 1
                print(f"  заказ {order.wb_order_id}: факт не записан — {exc}")
                continue
            pending += 1
            if pending >= BATCH:
                # Длинная транзакция на боевой базе держит блокировки. Пишем
                # порциями, как это делает начисление задним числом.
                await session.commit()
                pending = 0

        if args.apply:
            await session.commit()
            print("изменения записаны")
        else:
            await session.rollback()
            print("сухой прогон: ничего не записано, повторите с --apply")

    print(f"фактов создано: {created}, дат исправлено: {redated}")
    if skipped_no_seller:
        print(f"пропущено без селлера: {skipped_no_seller}")
    if skipped_early:
        print(f"пропущено как более ранние, чем --from: {skipped_early}")
    if failed:
        print(f"не удалось записать: {failed}")
    if by_day:
        print("работа по дням (то, что попадёт в счёт):")
        for day in sorted(by_day):
            if by_day[day]:
                print(f"  {day}: {by_day[day]}")


if __name__ == "__main__":
    asyncio.run(main())
