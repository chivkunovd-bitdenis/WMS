"""products: wb country of origin and shelf life fields

Revision ID: 20260816_0091
Revises: 20260816_0090
Create Date: 2026-08-16

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260816_0091"
down_revision = "20260816_0090"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products", sa.Column("wb_country_of_origin", sa.String(length=255), nullable=True)
    )
    op.add_column("products", sa.Column("wb_shelf_life", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "wb_shelf_life")
    op.drop_column("products", "wb_country_of_origin")
