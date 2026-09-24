"""WMS-469: per-product publication switch on an existing binding pool row.

Revision ID: 20260920_0307
Revises: 20260921_0490
Create Date: 2026-09-20 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260920_0307"
down_revision: str | Sequence[str] | None = "20260921_0490"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NULL deliberately preserves the pre-WMS-469 interpretation through the
    # Product-level flags. New saves make this value explicit per binding.
    op.add_column(
        "fbs_binding_stock_pools",
        sa.Column("publish_enabled", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("fbs_binding_stock_pools", "publish_enabled")
