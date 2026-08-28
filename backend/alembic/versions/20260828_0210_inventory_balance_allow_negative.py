"""Снять запрет отрицательного остатка: минус нужен подтверждённой доставке FBS.

Решение владельца от 28.08.2026, третий из трёх обсуждавшихся путей.

Столкнулись два замысла. Волна складской структуры запретила отрицательный
остаток на уровне базы — минус на полке бессмыслен. А эталон, который на бою,
наоборот требует минуса при подтверждённой доставке FBS: маркетплейс сказал, что
товар уехал, значит на складе его нет независимо от того, что думает учёт.
Отказать там значит подвесить поставку навсегда и оставить призрачный остаток,
а минус — это честная запись расхождения, которую потом разбирают инвентаризацией.

Проверка в базе не умеет спрашивать, кто её вызвал, поэтому защита переехала на
уровень сервиса: `record_movement_and_adjust_balance` по умолчанию в минус не
пускает, и делает это условием внутри самого запроса — то есть остаётся
устойчивой к одновременным списаниям. Явный обход есть ровно у одного вызова.

Это удаляющая миграция, и она здесь по прямому решению владельца, а не по
инициативе исполнителя.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision = "20260828_0210"
down_revision: str | Sequence[str] | None = "20260828_0190"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINTS = (
    "ck_inventory_balance_quantity_nonnegative",
    "ck_inventory_balance_quantity_unpacked_nonnegative",
    "ck_inventory_balance_quantity_packed_nonnegative",
)


def upgrade() -> None:
    for name in _CONSTRAINTS:
        # Ограничения могло не быть: базы разных контуров получили разный набор
        # ревизий. Отсутствие — не повод валить накатку.
        op.execute(f"ALTER TABLE inventory_balances DROP CONSTRAINT IF EXISTS {name}")


def downgrade() -> None:
    op.create_check_constraint(
        "ck_inventory_balance_quantity_nonnegative", "inventory_balances", "quantity >= 0"
    )
    op.create_check_constraint(
        "ck_inventory_balance_quantity_unpacked_nonnegative",
        "inventory_balances",
        "quantity_unpacked >= 0",
    )
    op.create_check_constraint(
        "ck_inventory_balance_quantity_packed_nonnegative",
        "inventory_balances",
        "quantity_packed >= 0",
    )
