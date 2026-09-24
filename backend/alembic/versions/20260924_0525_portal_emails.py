"""Allow one email in the FF portal and one in the seller portal.

Revision ID: 20260924_0525
Revises: 20260921_0490
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260924_0525"
down_revision = "20260921_0490"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    op.create_index(
        "ix_users_ff_email", "users", ["email"], unique=True,
        postgresql_where=sa.text("role <> 'fulfillment_seller' AND email IS NOT NULL"),
        sqlite_where=sa.text("role <> 'fulfillment_seller' AND email IS NOT NULL"),
    )
    op.create_index(
        "ix_users_seller_email", "users", ["email"], unique=True,
        postgresql_where=sa.text("role = 'fulfillment_seller' AND email IS NOT NULL"),
        sqlite_where=sa.text("role = 'fulfillment_seller' AND email IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_users_seller_email", table_name="users")
    op.drop_index("ix_users_ff_email", table_name="users")
    op.create_index("ix_users_email", "users", ["email"], unique=True)
