"""notifications table for in-app notification bus

Revision ID: 20260626_0049
Revises: 20260626_0048
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260626_0049"
down_revision = "20260626_0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("recipient_type", sa.String(length=32), nullable=False),
        sa.Column("recipient_id", sa.String(length=64), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("link", sa.String(length=512), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_notifications_tenant_id", "notifications", ["tenant_id"])
    op.create_index(
        "ix_notifications_recipient",
        "notifications",
        ["tenant_id", "recipient_type", "recipient_id"],
    )
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])


def downgrade() -> None:
    op.drop_table("notifications")
