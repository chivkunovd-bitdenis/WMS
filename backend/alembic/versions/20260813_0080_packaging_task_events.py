"""Packaging task operator events.

Revision ID: 20260813_0080
Revises: 20260812_0079
Create Date: 2026-08-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260813_0080"
down_revision: str | Sequence[str] | None = "20260812_0079"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "packaging_task_events",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("task_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("event_sequence", sa.Integer(), nullable=False),
        sa.Column("line_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("storage_location_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reversed_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["line_id"], ["packaging_task_lines.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["reversed_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["storage_location_id"], ["storage_locations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["packaging_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "task_id",
            "event_sequence",
            name="uq_packaging_task_events_task_sequence",
        ),
    )
    op.create_index("ix_packaging_task_events_action", "packaging_task_events", ["action"])
    op.create_index("ix_packaging_task_events_created_at", "packaging_task_events", ["created_at"])
    op.create_index(
        "ix_packaging_task_events_created_by_user_id",
        "packaging_task_events",
        ["created_by_user_id"],
    )
    op.create_index("ix_packaging_task_events_line_id", "packaging_task_events", ["line_id"])
    op.create_index("ix_packaging_task_events_product_id", "packaging_task_events", ["product_id"])
    op.create_index("ix_packaging_task_events_task_id", "packaging_task_events", ["task_id"])
    op.create_index("ix_packaging_task_events_tenant_id", "packaging_task_events", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_packaging_task_events_tenant_id", table_name="packaging_task_events")
    op.drop_index("ix_packaging_task_events_task_id", table_name="packaging_task_events")
    op.drop_index("ix_packaging_task_events_product_id", table_name="packaging_task_events")
    op.drop_index("ix_packaging_task_events_line_id", table_name="packaging_task_events")
    op.drop_index("ix_packaging_task_events_created_by_user_id", table_name="packaging_task_events")
    op.drop_index("ix_packaging_task_events_created_at", table_name="packaging_task_events")
    op.drop_index("ix_packaging_task_events_action", table_name="packaging_task_events")
    op.drop_table("packaging_task_events")
