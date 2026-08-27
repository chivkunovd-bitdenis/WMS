"""Record the user who initiated an inventory movement, when known.

Revision ID: 20260828_0116
Revises: 20260827_0115
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260828_0116"
down_revision: str | Sequence[str] | None = "20260827_0115"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "inventory_movements",
        sa.Column(
            "actor_user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_inventory_movements_actor_user_id",
        "inventory_movements",
        ["actor_user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_inventory_movements_actor_user_id",
        table_name="inventory_movements",
    )
    op.drop_column("inventory_movements", "actor_user_id")
