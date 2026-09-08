"""WMS-381: дата оплаченной подписки у организации.

Одно поле вместо таблицы подписок: срок считается вычитанием, а не журналом.
NULL означает «подписка не применяется» — все существующие организации после
миграции работают ровно как работали.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260906_1100"
down_revision = "20260905_0254"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("subscription_paid_until", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenants", "subscription_paid_until")
