"""Inbound returns, stored product volume, and FF-added fact lines.

Revision ID: 20260812_0079
Revises: 20260812_0078
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260812_0079"
down_revision: str | Sequence[str] | None = "20260812_0078"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("volume_liters", sa.Float(), nullable=True))
    op.execute(
        """
        UPDATE products
        SET volume_liters = (length_mm * width_mm * height_mm) / 1000000.0
        WHERE length_mm IS NOT NULL
          AND width_mm IS NOT NULL
          AND height_mm IS NOT NULL
          AND length_mm > 0
          AND width_mm > 0
          AND height_mm > 0
        """
    )
    op.add_column(
        "inbound_intake_requests",
        sa.Column(
            "operation_type",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'inbound'"),
        ),
    )
    op.add_column(
        "inbound_intake_lines",
        sa.Column(
            "added_by_fulfillment",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("inbound_intake_lines", "added_by_fulfillment")
    op.drop_column("inbound_intake_requests", "operation_type")
    op.drop_column("products", "volume_liters")
