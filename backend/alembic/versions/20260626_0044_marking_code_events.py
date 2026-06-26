"""marking_code_events journal

Revision ID: 20260626_0044
Revises: 20260626_0043
Create Date: 2026-06-26

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260626_0044"
down_revision = "20260626_0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "marking_code_events",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("seller_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("code_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("pool_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("packaging_task_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("packaging_task_line_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("document_number", sa.String(length=32), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("copies", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("reason", sa.String(length=512), nullable=True),
        sa.Column("meta_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["code_id"], ["marking_codes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["packaging_task_id"], ["packaging_tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["packaging_task_line_id"], ["packaging_task_lines.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["pool_id"], ["marking_pools.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_marking_code_events_tenant_id", "marking_code_events", ["tenant_id"])
    op.create_index("ix_marking_code_events_code_id", "marking_code_events", ["code_id"])
    op.create_index("ix_marking_code_events_pool_id", "marking_code_events", ["pool_id"])
    op.create_index(
        "ix_marking_code_events_packaging_task_id",
        "marking_code_events",
        ["packaging_task_id"],
    )
    op.create_index(
        "ix_marking_code_events_created_at",
        "marking_code_events",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_marking_code_events_created_at", table_name="marking_code_events")
    op.drop_index("ix_marking_code_events_packaging_task_id", table_name="marking_code_events")
    op.drop_index("ix_marking_code_events_pool_id", table_name="marking_code_events")
    op.drop_index("ix_marking_code_events_code_id", table_name="marking_code_events")
    op.drop_index("ix_marking_code_events_tenant_id", table_name="marking_code_events")
    op.drop_table("marking_code_events")
