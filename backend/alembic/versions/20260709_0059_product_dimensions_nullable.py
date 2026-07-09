"""Allow NULL product dimensions (unknown volume for billing)."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260709_0059"
down_revision = "20260707_0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "products",
        "length_mm",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.alter_column(
        "products",
        "width_mm",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.alter_column(
        "products",
        "height_mm",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    op.execute("UPDATE products SET length_mm = 10 WHERE length_mm IS NULL")
    op.execute("UPDATE products SET width_mm = 10 WHERE width_mm IS NULL")
    op.execute("UPDATE products SET height_mm = 10 WHERE height_mm IS NULL")
    op.alter_column(
        "products",
        "length_mm",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.alter_column(
        "products",
        "width_mm",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.alter_column(
        "products",
        "height_mm",
        existing_type=sa.Integer(),
        nullable=False,
    )
