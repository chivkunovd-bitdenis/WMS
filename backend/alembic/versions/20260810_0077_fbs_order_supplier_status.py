"""Разделить seller-side и WB-side статусы FBS-заказа.

Revision ID: 20260810_0077
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260810_0077"
down_revision = "20260809_0076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fbs_orders", sa.Column("supplier_status", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("fbs_orders", "supplier_status")
