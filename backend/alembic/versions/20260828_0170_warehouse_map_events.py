"""Warehouse map placement journal.

Revision ID: 20260828_0170
Revises: 20260828_0130
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260828_0170"
down_revision = "20260828_0130"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "warehouse_map_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("subject", sa.String(length=512), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("from_label", sa.String(length=255), nullable=False),
        sa.Column("to_label", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_warehouse_map_events_tenant_id",
        "warehouse_map_events",
        ["tenant_id"],
    )
    op.create_index(
        "ix_warehouse_map_events_warehouse_id",
        "warehouse_map_events",
        ["warehouse_id"],
    )
    op.create_index(
        "ix_warehouse_map_events_actor_user_id",
        "warehouse_map_events",
        ["actor_user_id"],
    )
    op.create_index(
        "ix_warehouse_map_events_created_at",
        "warehouse_map_events",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_warehouse_map_events_created_at", table_name="warehouse_map_events")
    op.drop_index("ix_warehouse_map_events_actor_user_id", table_name="warehouse_map_events")
    op.drop_index("ix_warehouse_map_events_warehouse_id", table_name="warehouse_map_events")
    op.drop_index("ix_warehouse_map_events_tenant_id", table_name="warehouse_map_events")
    op.drop_table("warehouse_map_events")
