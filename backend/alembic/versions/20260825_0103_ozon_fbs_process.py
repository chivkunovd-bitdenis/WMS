"""support Ozon FBS carriage and product country

Revision ID: 20260825_0103
Revises: 20260825_0102
"""

import sqlalchemy as sa

from alembic import op

revision = "20260825_0103"
down_revision = "20260825_0102"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "fbs_supplies",
        "wb_supply_id",
        existing_type=sa.String(length=64),
        nullable=True,
    )
    op.add_column(
        "products",
        sa.Column("country_of_origin_iso_code", sa.String(length=2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("products", "country_of_origin_iso_code")
    op.execute(
        "UPDATE fbs_supplies SET wb_supply_id = external_supply_id "
        "WHERE wb_supply_id IS NULL AND external_supply_id IS NOT NULL"
    )
    op.execute(
        "UPDATE fbs_supplies SET wb_supply_id = "
        "'OZON-LEGACY-' || CAST(id AS VARCHAR) WHERE wb_supply_id IS NULL"
    )
    op.alter_column(
        "fbs_supplies",
        "wb_supply_id",
        existing_type=sa.String(length=64),
        nullable=False,
    )
