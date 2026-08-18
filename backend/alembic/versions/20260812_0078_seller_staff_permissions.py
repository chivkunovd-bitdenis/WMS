"""seller staff permissions for seller cabinet users

Revision ID: 20260812_0078
Revises: 20260812_0077
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260812_0078"
down_revision = "20260812_0077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "seller_staff_permissions",
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("can_documents", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("can_products", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("can_honest_sign", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("can_settings", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_staff", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    for col in (
        "can_documents",
        "can_products",
        "can_honest_sign",
        "can_settings",
        "can_staff",
    ):
        op.alter_column("seller_staff_permissions", col, server_default=None)


def downgrade() -> None:
    op.drop_table("seller_staff_permissions")
