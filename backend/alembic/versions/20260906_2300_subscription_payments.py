"""WMS-382: платежи за подписку через ЮKassa.

Таблица нужна ровно для одного: отличить «эту оплату уже засчитали» от «оплатили
ещё раз». Уникальность по идентификатору платежа в ЮKassa — вся защита от
двойного продления за одни деньги.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260906_2300"
down_revision = "20260906_1100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscription_payments",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("provider_payment_id", sa.String(length=255), nullable=False),
        sa.Column("amount_rub", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, index=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_subscription_payments_provider_payment_id",
        "subscription_payments",
        ["provider_payment_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_subscription_payments_provider_payment_id",
        table_name="subscription_payments",
    )
    op.drop_table("subscription_payments")
