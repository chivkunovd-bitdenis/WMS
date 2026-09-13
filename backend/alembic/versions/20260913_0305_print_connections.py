"""WMS-442: narrowly scoped computer/OS queue pairing."""
from alembic import op
import sqlalchemy as sa

revision = "20260913_0305"
down_revision = "20260911_0304"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "print_connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE")),
        sa.Column("warehouse_id", sa.Uuid(), sa.ForeignKey("warehouses.id", ondelete="CASCADE")),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("pairing_hash", sa.String(64), unique=True),
        sa.Column("pairing_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("queue_name", sa.String(127), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("paired_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
    )
    op.create_index("ix_print_connections_tenant_id", "print_connections", ["tenant_id"])
    op.create_index("ix_print_connections_warehouse_id", "print_connections", ["warehouse_id"])
    op.create_index("uq_print_connection_destination", "print_connections", ["warehouse_id"],
                    unique=True, postgresql_where=sa.text("is_default = true"),
                    sqlite_where=sa.text("is_default = 1"))


def downgrade() -> None:
    op.drop_table("print_connections")
