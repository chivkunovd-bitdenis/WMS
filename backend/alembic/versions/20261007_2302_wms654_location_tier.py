"""WMS-654: persist an optional tier in a storage location address.

Revision ID: 20261007_2302
Revises: 20261001_2301
"""

from alembic import op
import sqlalchemy as sa


revision = "20261007_2302"
down_revision = "20261001_2301"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("storage_locations", sa.Column("tier", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("storage_locations", "tier")
