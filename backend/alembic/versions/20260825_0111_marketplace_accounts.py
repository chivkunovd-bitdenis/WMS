"""add generic marketplace account storage

Revision ID: 20260825_0101
Revises: 20260823_0100
"""

from alembic import op
import sqlalchemy as sa


revision = "20260825_0111"
down_revision = "20260823_0100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "marketplace_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("seller_id", sa.Uuid(), nullable=False),
        sa.Column("marketplace", sa.String(length=32), nullable=False),
        sa.Column("account_slot", sa.String(length=64), nullable=False, server_default="primary"),
        sa.Column("external_account_id", sa.String(length=255), nullable=True),
        sa.Column("secret_encrypted", sa.String(length=4096), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("validation_status", sa.String(length=24), nullable=False, server_default="not_configured"),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_validation_error_code", sa.String(length=64), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_error_code", sa.String(length=64), nullable=True),
        sa.Column("credentials_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disconnected_by_user_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint("marketplace <> ''", name="ck_marketplace_accounts_marketplace_nonempty"),
        sa.CheckConstraint("account_slot <> ''", name="ck_marketplace_accounts_slot_nonempty"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["disconnected_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "seller_id", "marketplace", "account_slot", name="uq_marketplace_accounts_scope_slot"),
    )
    op.create_index("ix_marketplace_accounts_tenant_id", "marketplace_accounts", ["tenant_id"])
    op.create_index("ix_marketplace_accounts_seller_id", "marketplace_accounts", ["seller_id"])
    op.create_index(
        "ix_marketplace_accounts_tenant_seller_marketplace_active",
        "marketplace_accounts", ["tenant_id", "seller_id", "marketplace", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_marketplace_accounts_tenant_seller_marketplace_active", table_name="marketplace_accounts")
    op.drop_index("ix_marketplace_accounts_seller_id", table_name="marketplace_accounts")
    op.drop_index("ix_marketplace_accounts_tenant_id", table_name="marketplace_accounts")
    op.drop_table("marketplace_accounts")
