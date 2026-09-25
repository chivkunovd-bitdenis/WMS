"""WMS-483: distinguish explicit operator units rules from legacy zero pools.

Revision ID: 20260920_0255
Revises: 20260913_0306
"""

import sqlalchemy as sa
from alembic import op

revision = "20260920_0255"
down_revision = "20260913_0306"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing positive quantities remain valid limits in application code.
    # A historical zero has no proof of operator intent and stays unconfigured.
    op.add_column(
        "fbs_binding_stock_pools",
        sa.Column("units_configured", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("fbs_binding_stock_pools", "units_configured")
