"""Store WB supply id on FBS orders.

Revision ID: 20260811_0078
Revises: 20260811_0077
Create Date: 2026-08-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260811_0078"
down_revision: str | Sequence[str] | None = "20260811_0077"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "fbs_orders",
        sa.Column("wb_supply_id", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_fbs_orders_wb_supply_id", "fbs_orders", ["wb_supply_id"])


def downgrade() -> None:
    op.drop_index("ix_fbs_orders_wb_supply_id", table_name="fbs_orders")
    op.drop_column("fbs_orders", "wb_supply_id")
