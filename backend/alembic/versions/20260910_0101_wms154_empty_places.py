"""WMS-154: confirmed empty places belong to the existing count document."""
import sqlalchemy as sa

from alembic import op

revision = "20260910_0101"
down_revision = "20260910_0100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inventory_counts", sa.Column("empty_places", sa.JSON(), nullable=False,
                                               server_default=sa.text("'[]'")))


def downgrade() -> None:
    op.drop_column("inventory_counts", "empty_places")
