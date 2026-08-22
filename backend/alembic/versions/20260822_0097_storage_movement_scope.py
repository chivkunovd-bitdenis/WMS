"""Mark operational warehouses used by storage measurements."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260822_0097"
down_revision = "20260822_0096"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "warehouses",
        sa.Column("is_operational", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.execute(
        sa.text(
            """
            UPDATE warehouses
            SET is_operational = FALSE
            WHERE name = 'FBS WB'
               OR name LIKE 'FBS WB %'
               OR code LIKE 'fbs-wb-%'
            """
        )
    )


def downgrade() -> None:
    op.drop_column("warehouses", "is_operational")
