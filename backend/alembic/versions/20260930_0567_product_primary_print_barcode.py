"""WMS-593: operator-selected product label barcode.

Revision ID: 20260930_0567
Revises: 20260930_0566
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260930_0567"
down_revision = "20260930_0566"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products", sa.Column("primary_print_barcode", sa.String(length=64), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("products", "primary_print_barcode")
