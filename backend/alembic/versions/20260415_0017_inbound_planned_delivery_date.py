"""inbound planned_delivery_date

Revision ID: 0017
Revises: 0016
Create Date: 2026-04-15

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, Sequence[str], None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "inbound_intake_requests",
        sa.Column("planned_delivery_date", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("inbound_intake_requests", "planned_delivery_date")

