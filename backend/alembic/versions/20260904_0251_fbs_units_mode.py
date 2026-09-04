"""fbs units allocation mode: per-warehouse quota in pieces

Режим «остаток по штукам». Доля свободного остатка остаётся основным способом,
но у продавца бывает согласованная разбивка по направлениям в конкретных числах,
которая в сетку кратных десяти процентов не ложится.

Две колонки:

* ``products.fbs_units_mode`` — какой режим у товара.
* ``fbs_binding_stock_pools.allocated_at`` — момент, с которого считается расход
  квоты. Сама квота лежит в существующей ``quantity``; заказы её не уменьшают,
  остаток считается выводом из журнала ``fbs_stock_pool_debits``.

Revision ID: 20260904_0251
Revises: 20260903_0250
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260904_0251"
down_revision: str | Sequence[str] | None = "20260903_0250"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column(
            "fbs_units_mode",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "fbs_binding_stock_pools",
        sa.Column("allocated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("fbs_binding_stock_pools", "allocated_at")
    op.drop_column("products", "fbs_units_mode")
