"""marking_reprint_requests for defect / reprint queue

Revision ID: 20260626_0048
Revises: 20260626_0047
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260626_0048"
down_revision = "20260626_0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "marking_reprint_requests",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("code_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("packaging_task_line_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("reason", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("resolved_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["code_id"], ["marking_codes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["packaging_task_line_id"], ["packaging_task_lines.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_marking_reprint_requests_tenant_id",
        "marking_reprint_requests",
        ["tenant_id"],
    )
    op.create_index(
        "ix_marking_reprint_requests_code_id",
        "marking_reprint_requests",
        ["code_id"],
    )
    op.create_index(
        "ix_marking_reprint_requests_packaging_task_line_id",
        "marking_reprint_requests",
        ["packaging_task_line_id"],
    )
    op.create_index(
        "ix_marking_reprint_requests_created_at",
        "marking_reprint_requests",
        ["created_at"],
    )
    op.alter_column("marking_reprint_requests", "status", server_default=None)


def downgrade() -> None:
    op.drop_table("marking_reprint_requests")
