"""WMS-351: independent Ozon publication switch with unchanged legacy values."""

from alembic import op
import sqlalchemy as sa

revision = "20260908_0256"
down_revision = "20260905_0254"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("fbs_ozon_stock_sync_enabled", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "fbs_ozon_stock_sync_enabled")
