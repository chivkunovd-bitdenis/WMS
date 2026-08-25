"""preserve the operator route order of imported Ozon giveouts

Revision ID: 20260825_0107
Revises: 20260825_0106
"""

import sqlalchemy as sa

from alembic import op

revision = "20260825_0107"
down_revision = "20260825_0106"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inbound_ozon_return_giveouts",
        sa.Column("route_position", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("inbound_ozon_return_giveouts", "route_position")
