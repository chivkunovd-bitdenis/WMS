"""Add schema fields for manual FBS KIZ binding.

Revision ID: 20260810_0077
Revises: 20260809_0076
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260810_0077"
down_revision = "20260809_0076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fbs_order_markings",
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_fbs_order_markings_tenant_id",
        "fbs_order_markings",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.execute(
        sa.text(
            """
            UPDATE fbs_order_markings AS marking
            SET tenant_id = orders.tenant_id
            FROM fbs_orders AS orders
            WHERE marking.order_id = orders.id
            """
        )
    )
    op.alter_column(
        "fbs_order_markings",
        "tenant_id",
        existing_type=sa.Uuid(as_uuid=True),
        nullable=False,
    )
    op.create_index(
        "ix_fbs_order_markings_tenant_id",
        "fbs_order_markings",
        ["tenant_id"],
    )
    op.add_column(
        "fbs_order_markings",
        sa.Column(
            "source",
            sa.String(length=16),
            nullable=False,
            # Существующие строки созданы печатью ЧЗ из пула
            # (fbs_order_tape_print_service._assign_printed_code_to_order),
            # поэтому дефолт 'pool'. Внесение оператором пишет 'operator' явно.
            server_default="pool",
        ),
    )
    op.add_column(
        "fbs_order_markings",
        sa.Column("created_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_fbs_order_markings_created_by_user_id",
        "fbs_order_markings",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "fbs_order_markings",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "uq_fbs_order_markings_tenant_kind_value",
        "fbs_order_markings",
        ["tenant_id", "kind", "value"],
        unique=True,
        postgresql_where=sa.text("meta_status <> 'rejected'"),
    )

    op.add_column(
        "marking_codes",
        sa.Column("source", sa.String(length=16), nullable=False, server_default="pool"),
    )

    op.add_column(
        "packaging_task_lines",
        sa.Column("qty_marking_external", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("packaging_task_lines", "qty_marking_external")

    op.drop_column("marking_codes", "source")

    op.drop_index(
        "uq_fbs_order_markings_tenant_kind_value",
        table_name="fbs_order_markings",
    )
    op.drop_column("fbs_order_markings", "created_at")
    op.drop_constraint(
        "fk_fbs_order_markings_created_by_user_id",
        "fbs_order_markings",
        type_="foreignkey",
    )
    op.drop_column("fbs_order_markings", "created_by_user_id")
    op.drop_column("fbs_order_markings", "source")
    op.drop_index("ix_fbs_order_markings_tenant_id", table_name="fbs_order_markings")
    op.drop_constraint(
        "fk_fbs_order_markings_tenant_id",
        "fbs_order_markings",
        type_="foreignkey",
    )
    op.drop_column("fbs_order_markings", "tenant_id")
