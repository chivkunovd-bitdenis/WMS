"""staff packaging rate, task billing snapshot, packaging permission

Revision ID: 0038
Revises: 0037
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0038"
down_revision: str | Sequence[str] | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "packaging_rate_kopecks",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.alter_column("users", "packaging_rate_kopecks", server_default=None)

    op.add_column(
        "ff_staff_permissions",
        sa.Column("can_packaging", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("ff_staff_permissions", "can_packaging", server_default=None)

    op.add_column(
        "packaging_tasks",
        sa.Column("created_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.add_column(
        "packaging_tasks",
        sa.Column("completed_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.add_column(
        "packaging_tasks",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "packaging_tasks",
        sa.Column("billing_units_packed", sa.Integer(), nullable=True),
    )
    op.add_column(
        "packaging_tasks",
        sa.Column("billing_rate_kopecks", sa.Integer(), nullable=True),
    )
    op.add_column(
        "packaging_tasks",
        sa.Column("billing_earned_kopecks", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_packaging_tasks_created_by_user_id",
        "packaging_tasks",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_packaging_tasks_completed_by_user_id",
        "packaging_tasks",
        "users",
        ["completed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_packaging_tasks_completed_by_user_id"),
        "packaging_tasks",
        ["completed_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_packaging_tasks_completed_at"),
        "packaging_tasks",
        ["completed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_packaging_tasks_completed_at"), table_name="packaging_tasks")
    op.drop_index(
        op.f("ix_packaging_tasks_completed_by_user_id"),
        table_name="packaging_tasks",
    )
    op.drop_constraint(
        "fk_packaging_tasks_completed_by_user_id",
        "packaging_tasks",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_packaging_tasks_created_by_user_id",
        "packaging_tasks",
        type_="foreignkey",
    )
    op.drop_column("packaging_tasks", "billing_earned_kopecks")
    op.drop_column("packaging_tasks", "billing_rate_kopecks")
    op.drop_column("packaging_tasks", "billing_units_packed")
    op.drop_column("packaging_tasks", "completed_at")
    op.drop_column("packaging_tasks", "completed_by_user_id")
    op.drop_column("packaging_tasks", "created_by_user_id")
    op.drop_column("ff_staff_permissions", "can_packaging")
    op.drop_column("users", "packaging_rate_kopecks")
