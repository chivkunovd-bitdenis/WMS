"""Add per-product FBS stock sync flag and limit.

Revision ID: 20260809_0075
Revises: 20260806_0074
Create Date: 2026-08-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260809_0075"
down_revision: str | Sequence[str] | None = "20260806_0074"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column(
            "fbs_stock_sync_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "products",
        sa.Column(
            "fbs_stock_limit",
            sa.Integer(),
            nullable=True,
            server_default=sa.text("null"),
        ),
    )


def downgrade() -> None:
    op.drop_column("products", "fbs_stock_limit")
    op.drop_column("products", "fbs_stock_sync_enabled")
