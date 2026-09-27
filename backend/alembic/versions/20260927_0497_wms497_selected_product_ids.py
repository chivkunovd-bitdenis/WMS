"""WMS-497: inventory count remembers the products selected at creation."""
import sqlalchemy as sa

from alembic import op

revision = "20260927_0497"
down_revision = "20260925_0530"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inventory_counts",
        sa.Column("selected_product_ids", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("inventory_counts", "selected_product_ids")
