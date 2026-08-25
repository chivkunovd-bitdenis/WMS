"""preserve Ozon FBS composition through packaging and reversal

Revision ID: 20260825_0105
Revises: 20260825_0104
"""

import sqlalchemy as sa

from alembic import op

revision = "20260825_0105"
down_revision = "20260825_0104"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fbs_packaging_fulfillments",
        sa.Column("ozon_packed_units_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "fbs_shipment_reversal_ledger",
        sa.Column("ozon_positions_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("fbs_shipment_reversal_ledger", "ozon_positions_json")
    op.drop_column("fbs_packaging_fulfillments", "ozon_packed_units_json")
