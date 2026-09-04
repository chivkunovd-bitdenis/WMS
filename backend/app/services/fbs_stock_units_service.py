"""Остаток квоты в режиме «остаток по штукам».

Оператор задаёт по каждому складу WB число: сколько штук этого товара отдаём в
это направление. Дальше квота расходуется заказами **этого** склада и никогда не
растёт сама — приехала новая партия, числа остались прежними, пока их не поднимут
руками. Соседний склад в чужую квоту залезть не может.

Ключевое решение здесь одно: **остаток квоты нигде не хранится, он выводится**.

Соблазн держать счётчик и уменьшать его на каждом заказе велик, и ровно так был
сделан старый пул: `quantity -= 1` при импорте заказа. Он не восстанавливался при
отмене, и остаток разъезжался с реальностью навсегда — починить такое можно было
только руками. Поэтому `quantity` теперь означает «сколько выделил оператор» и
меняется только когда оператор сам это делает, а съеденное считается по журналу
`fbs_stock_pool_debits`, где уже есть строка на каждый заказ и уникальность по
`order_id`.

Что даёт вывод вместо счётчика:

* отменили заказ — он перестал попадать в выборку, квота вернулась сама, без
  отдельного события и без риска его потерять;
* заказ пришёл дважды на автоопросе — в журнале всё равно одна строка;
* пересчёт всегда даёт одно и то же число, сколько бы раз его ни запросили.

Отмена уже после передачи поставки квоту НЕ возвращает, и это то же правило, что
и для физического остатка (`OWN-2026-08-31-06`): товар уехал, вернуть его в
остаток может только отдельный документ возврата. Признак «уехал» — проставленное
движение списания в журнале сторнирования.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fbs_binding_stock_pool import FbsBindingStockPool
from app.models.fbs_order import FBS_ORDER_STATUS_CANCELLED, FbsOrder
from app.models.fbs_shipment_reversal_ledger import FbsShipmentReversalLedger
from app.models.fbs_stock_pool_debit import FbsStockPoolDebit


def _allocated_since(pool: FbsBindingStockPool) -> datetime:
    """С какого момента считать расход квоты этого пула.

    Обычно это `allocated_at`. У строк, залитых в базу напрямую (первое включение
    продавцам делалось SQL-ом, до появления экрана), отметки может не быть — тогда
    берётся момент последней записи строки. Считать «с начала времён» нельзя: в
    журнале лежат списания за август, и они съели бы свежую квоту целиком.
    """
    return pool.allocated_at or pool.updated_at or pool.created_at


def _consumed_stmt(pool: FbsBindingStockPool) -> Select[tuple[int]]:
    """Сколько штук этой квоты уже съедено с момента выделения."""
    shipped = (
        select(FbsShipmentReversalLedger.id)
        .where(
            FbsShipmentReversalLedger.fbs_order_id == FbsOrder.id,
            FbsShipmentReversalLedger.shipment_movement_id.is_not(None),
        )
        .exists()
    )
    return (
        select(func.coalesce(func.sum(FbsStockPoolDebit.quantity_debited), 0))
        .join(FbsOrder, FbsOrder.id == FbsStockPoolDebit.order_id)
        .where(
            FbsStockPoolDebit.pool_id == pool.id,
            FbsStockPoolDebit.created_at >= _allocated_since(pool),
            # Отменённый заказ квоту не держит — если товар не уехал. Уехал
            # (списание проведено) — держит, возврат оформляется документом.
            or_(FbsOrder.status != FBS_ORDER_STATUS_CANCELLED, shipped),
        )
    )


async def consumed_units(session: AsyncSession, pool: FbsBindingStockPool) -> int:
    return int(await session.scalar(_consumed_stmt(pool)) or 0)


async def remaining_units(session: AsyncSession, pool: FbsBindingStockPool) -> int:
    """Сколько ещё можно отдать в это направление. Никогда не меньше нуля."""
    return max(0, int(pool.quantity or 0) - await consumed_units(session, pool))


async def remaining_units_by_binding(
    session: AsyncSession,
    pool_rows: dict[uuid.UUID, FbsBindingStockPool],
) -> dict[uuid.UUID, int]:
    """Остаток квоты по каждой привязке: binding_id -> сколько штук осталось."""
    result: dict[uuid.UUID, int] = {}
    for binding_id, pool in pool_rows.items():
        result[binding_id] = await remaining_units(session, pool)
    return result
