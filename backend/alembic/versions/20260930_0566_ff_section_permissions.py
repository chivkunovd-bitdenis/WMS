"""WMS-594: independent fulfillment staff section access.

Revision ID: 20260930_0566
Revises: 20260929_0565
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260930_0566"
down_revision = "20260929_0565"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name in ("billing", "storage", "fbs", "honest_sign"):
        op.add_column(
            "ff_staff_permissions",
            sa.Column(f"can_{name}", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    # Existing staff keep the effective storage and FBS access they had before
    # these sections became independent. Billing and Honest Sign were admin only.
    op.execute(
        "UPDATE ff_staff_permissions SET can_storage = can_inventory, can_fbs = can_packaging"
    )


def downgrade() -> None:
    for name in ("honest_sign", "fbs", "storage", "billing"):
        op.drop_column("ff_staff_permissions", f"can_{name}")
