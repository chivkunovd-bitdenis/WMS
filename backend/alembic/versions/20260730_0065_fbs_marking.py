"""FBS order marking unique constraint (order_id, kind, value).

Revision ID: 20260730_0065
Revises: 20260730_0064
Create Date: 2026-07-30
"""

from __future__ import annotations

from alembic import op

revision = "20260730_0065"
down_revision = "20260730_0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_fbs_order_markings_order_kind_value",
        "fbs_order_markings",
        ["order_id", "kind", "value"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_fbs_order_markings_order_kind_value",
        "fbs_order_markings",
        type_="unique",
    )
