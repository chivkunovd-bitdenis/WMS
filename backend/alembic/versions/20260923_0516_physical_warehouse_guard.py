"""WMS-516: guard physical writes; legacy data repair is an explicit manifest run."""

from alembic import op
from app.db.physical_warehouse_guard import install_guards, remove_guards

revision = "20260923_0516"
down_revision = "20260921_0490"
branch_labels = None
depends_on = None


def upgrade() -> None:
    install_guards(op.get_bind())


def downgrade() -> None:
    remove_guards(op.get_bind())
