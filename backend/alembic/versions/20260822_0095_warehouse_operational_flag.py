"""Add an explicit operational-warehouse flag for reporting slices."""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260822_0095"
down_revision: str | Sequence[str] | None = "20260822_0094"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    op.add_column(
        "warehouses",
        sa.Column(
            "is_operational", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )
    op.execute(sa.text("UPDATE warehouses SET is_operational = FALSE WHERE name LIKE 'FBS WB %'"))

def downgrade() -> None:
    op.drop_column("warehouses", "is_operational")
