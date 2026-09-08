"""WMS-058: preserve actual Ozon pick source when no transfer is needed."""

import sqlalchemy as sa

from alembic import op

revision = "20260908_0255"
down_revision = "20260906_2300"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No backfill: old NULL-movement picks contain no evidence of their container.
    op.add_column(
        "fbs_order_product_picks", sa.Column("source_container_kind", sa.String(16), nullable=True)
    )
    op.add_column(
        "fbs_order_product_picks", sa.Column("source_container_id", sa.Uuid(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("fbs_order_product_picks", "source_container_id")
    op.drop_column("fbs_order_product_picks", "source_container_kind")
