"""WMS-588: persistent FBS assembly task aggregate.

Revision ID: 20260929_0565
Revises: 20260928_0564
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260929_0565"
down_revision = "20260928_0564"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fbs_assembly_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_fbs_assembly_tasks_tenant_idempotency",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "number",
            name="uq_fbs_assembly_tasks_tenant_number",
        ),
    )
    op.create_index(
        op.f("ix_fbs_assembly_tasks_tenant_id"),
        "fbs_assembly_tasks",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fbs_assembly_tasks_created_by_user_id"),
        "fbs_assembly_tasks",
        ["created_by_user_id"],
        unique=False,
    )

    op.create_table(
        "fbs_assembly_task_supplies",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("supply_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["fbs_assembly_tasks.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["supply_id"],
            ["fbs_supplies.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("task_id", "supply_id"),
        sa.UniqueConstraint(
            "supply_id",
            name="uq_fbs_assembly_task_supplies_supply_id",
        ),
    )


def downgrade() -> None:
    op.drop_table("fbs_assembly_task_supplies")
    op.drop_index(
        op.f("ix_fbs_assembly_tasks_created_by_user_id"),
        table_name="fbs_assembly_tasks",
    )
    op.drop_index(
        op.f("ix_fbs_assembly_tasks_tenant_id"),
        table_name="fbs_assembly_tasks",
    )
    op.drop_table("fbs_assembly_tasks")
