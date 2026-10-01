"""WMS-624: durable developer requests and recoverable Trello delivery.

Revision ID: 20261001_2301
Revises: 20260929_0565
"""
from alembic import op
import sqlalchemy as sa

revision = "20261001_2301"
down_revision = "20260929_0565"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "developer_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seller_id", sa.Uuid(), sa.ForeignKey("sellers.id", ondelete="SET NULL")),
        sa.Column("client_name", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("screen", sa.Text()),
        sa.Column("problem", sa.Text()),
        sa.Column("proposal", sa.Text()),
        sa.Column("page_url", sa.Text()),
        sa.Column("status", sa.String(16), nullable=False, server_default="review"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("delivery_state", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("trello_board_id", sa.String(128)),
        sa.Column("trello_card_id", sa.String(128), unique=True),
        sa.Column("create_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(64)),
        sa.Column("next_sync_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("lease_token", sa.Uuid()),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "created_by_user_id", "idempotency_key", name="uq_developer_requests_author_key"),
    )
    op.create_index("ix_developer_requests_author", "developer_requests", ["tenant_id", "created_by_user_id", "created_at"])
    op.create_index("ix_developer_requests_sync_due", "developer_requests", ["next_sync_at"])


def downgrade() -> None:
    op.drop_table("developer_requests")
