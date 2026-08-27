"""Record which user initiated an FBS WB operation, when known.

Revision ID: 20260827_0104
Revises: 20260826_0103
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260827_0104"
down_revision: str | Sequence[str] | None = "20260826_0103"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable: old rows have no way to know who acted, and background
    # reconciliation operations genuinely have no human actor.
    op.add_column(
        "fbs_wb_operations",
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_fbs_wb_operations_created_by_user",
        "fbs_wb_operations",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_fbs_wb_operations_created_by_user",
        "fbs_wb_operations",
        type_="foreignkey",
    )
    op.drop_column("fbs_wb_operations", "created_by_user_id")
