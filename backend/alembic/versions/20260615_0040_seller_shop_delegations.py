"""seller shop delegations + can_manage_seller_shops on users

Revision ID: 20260615_0040
Revises: 20260614_0039
Create Date: 2026-06-15

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260615_0040"
down_revision = "20260614_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "can_manage_seller_shops",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_table(
        "seller_shop_delegations",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("target_seller_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["target_seller_id"], ["sellers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "target_seller_id",
            name="uq_seller_shop_delegations_user_target",
        ),
    )
    op.create_index(
        op.f("ix_seller_shop_delegations_target_seller_id"),
        "seller_shop_delegations",
        ["target_seller_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_seller_shop_delegations_user_id"),
        "seller_shop_delegations",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_seller_shop_delegations_user_id"),
        table_name="seller_shop_delegations",
    )
    op.drop_index(
        op.f("ix_seller_shop_delegations_target_seller_id"),
        table_name="seller_shop_delegations",
    )
    op.drop_table("seller_shop_delegations")
    op.drop_column("users", "can_manage_seller_shops")
