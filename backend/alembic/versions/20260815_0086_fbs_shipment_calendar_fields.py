"""Add FBS shipment calendar planning fields.

Revision ID: 20260815_0086
Revises: 20260814_0085
Create Date: 2026-08-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260815_0086"
down_revision: str | Sequence[str] | None = "20260814_0085"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("fbs_shipment_cutoff_time", sa.Time(), nullable=True),
    )
    op.add_column(
        "fbs_supplies",
        sa.Column("planned_shipment_date", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("fbs_supplies", "planned_shipment_date")
    op.drop_column("tenants", "fbs_shipment_cutoff_time")
