"""ff_staff_permissions for fulfillment staff access blocks

Revision ID: 0035
Revises: 0034
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035"
down_revision: str | Sequence[str] | None = "0034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ff_staff_permissions",
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("can_settings", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_mp_shipments", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_reception", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_cells", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_inventory", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    for col in (
        "can_settings",
        "can_mp_shipments",
        "can_reception",
        "can_cells",
        "can_inventory",
    ):
        op.alter_column("ff_staff_permissions", col, server_default=None)


def downgrade() -> None:
    op.drop_table("ff_staff_permissions")
