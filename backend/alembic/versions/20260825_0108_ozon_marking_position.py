"""link Ozon marking codes to their posting positions

Revision ID: 20260825_0108
Revises: 20260825_0107
"""

import sqlalchemy as sa

from alembic import op

revision = "20260825_0108"
down_revision = "20260825_0107"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fbs_order_markings",
        sa.Column(
            "order_product_id",
            sa.Uuid(),
            sa.ForeignKey("fbs_order_products.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_fbs_order_markings_order_product_id",
        "fbs_order_markings",
        ["order_product_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fbs_order_markings_order_product_id",
        table_name="fbs_order_markings",
    )
    op.drop_column("fbs_order_markings", "order_product_id")
