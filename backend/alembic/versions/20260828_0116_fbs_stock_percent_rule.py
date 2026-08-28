"""FBS stock as a percentage rule instead of a stored absolute number

Revision ID: 20260828_0116
Revises: 20260827_0115

Раньше оператор задавал абсолютное число штук, доступных для FBS. Оно устаревало
в тот момент, когда на склад приезжала новая партия, и его приходилось править
руками. Теперь хранится правило — доля свободного остатка, а само число считается
на момент публикации.

Миграция ТОЛЬКО добавляющая, это условие изолированной выкатки: старая колонка
`products.fbs_stock_limit` и старое `fbs_binding_stock_pools.quantity` остаются на
месте. Пока они есть, откат — это откат кода, без обратной миграции данных.

`fbs_warehouse_bindings.served` заводится со значением `true` для уже существующих
привязок: сегодня заказы по любому привязанному складу считаются нашими, и
миграция не должна менять это поведение сама по себе.
"""

import sqlalchemy as sa

from alembic import op

revision = "20260828_0116"
down_revision = "20260827_0115"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Доля на все склады сразу — обычный случай: у фулфилмента один физический
    # склад, а склады в кабинете WB это направления отгрузки.
    op.add_column("products", sa.Column("fbs_percent", sa.Integer(), nullable=True))
    op.add_column(
        "products",
        sa.Column(
            "fbs_same_everywhere",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    # Своя доля по конкретному складу WB. NULL означает «доля не задана отдельно»
    # и отличается от нуля: ноль — это осознанное «сюда не публикуем».
    op.add_column(
        "fbs_binding_stock_pools", sa.Column("percent", sa.Integer(), nullable=True)
    )
    op.add_column(
        "fbs_warehouse_bindings",
        sa.Column("served", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("fbs_warehouse_bindings", "served")
    op.drop_column("fbs_binding_stock_pools", "percent")
    op.drop_column("products", "fbs_same_everywhere")
    op.drop_column("products", "fbs_percent")
