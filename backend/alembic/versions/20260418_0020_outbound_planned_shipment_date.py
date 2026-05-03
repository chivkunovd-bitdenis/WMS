"""outbound_shipment_requests.planned_shipment_date

Revision ID: 0020
Revises: 0019
Create Date: 2026-04-18

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "outbound_shipment_requests",
        sa.Column("planned_shipment_date", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("outbound_shipment_requests", "planned_shipment_date")
