# ruff: noqa: RUF002
"""fbs_supplies: флаг пропуска требования маркировки Честный знак

Revision ID: 20260821_0093
Revises: 20260820_0092
Create Date: 2026-08-21

При создании поставки WB может указать маркировку в optionalMeta вместо requiredMeta,
но система требует её сканирование. Для таких поставок оператор должен иметь возможность
явно пропустить требование маркировки Честный знак, чтобы не сканировать сотни кодов.

Флаг добавляющий: незаполненные данные остаются, пропуск касается только проверок
при переводе поставки между статусами и печати ленты заказов.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260821_0093"
down_revision: str | Sequence[str] | None = "20260820_0092"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Временная метка, когда был выставлен флаг пропуска маркировки
    op.add_column(
        "fbs_supplies",
        sa.Column("honest_sign_skipped_at", sa.DateTime(timezone=True), nullable=True),
    )
    # UUID пользователя, который выставил флаг
    op.add_column(
        "fbs_supplies",
        sa.Column("honest_sign_skipped_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    # Создаём FK на таблицу users с каскадным удалением значения на NULL
    op.create_foreign_key(
        "fk_fbs_supplies_honest_sign_skipped_by_user_id",
        "fbs_supplies",
        "users",
        ["honest_sign_skipped_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_fbs_supplies_honest_sign_skipped_by_user_id",
        "fbs_supplies",
        type_="foreignkey",
    )
    op.drop_column("fbs_supplies", "honest_sign_skipped_by_user_id")
    op.drop_column("fbs_supplies", "honest_sign_skipped_at")
