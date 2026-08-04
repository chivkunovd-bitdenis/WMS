"""Add marking print batches ('iterations') and link marking_code_events to them.

Revision ID: 20260710_0061
Revises: 20260710_0060
Create Date: 2026-07-10

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260710_0061"
down_revision = "20260710_0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "marking_print_batches",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("seller_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("packaging_task_line_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("requested_quantity", sa.Integer(), nullable=False),
        sa.Column("printed_quantity", sa.Integer(), nullable=False),
        sa.Column("layout_json", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["packaging_task_line_id"], ["packaging_task_lines.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_marking_print_batches_tenant_id", "marking_print_batches", ["tenant_id"]
    )
    op.create_index(
        "ix_marking_print_batches_seller_id", "marking_print_batches", ["seller_id"]
    )
    op.create_index(
        "ix_marking_print_batches_product_id", "marking_print_batches", ["product_id"]
    )
    op.create_index(
        "ix_marking_print_batches_packaging_task_line_id",
        "marking_print_batches",
        ["packaging_task_line_id"],
    )
    op.create_index(
        "ix_marking_print_batches_created_at", "marking_print_batches", ["created_at"]
    )

    op.add_column(
        "marking_code_events",
        sa.Column("print_batch_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.add_column(
        "marking_code_events",
        sa.Column("position_in_batch", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_marking_code_events_print_batch_id",
        "marking_code_events",
        ["print_batch_id"],
    )
    op.create_foreign_key(
        "fk_marking_code_events_print_batch_id",
        "marking_code_events",
        "marking_print_batches",
        ["print_batch_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_marking_code_events_print_batch_id",
        "marking_code_events",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_marking_code_events_print_batch_id", table_name="marking_code_events"
    )
    op.drop_column("marking_code_events", "position_in_batch")
    op.drop_column("marking_code_events", "print_batch_id")

    op.drop_index(
        "ix_marking_print_batches_created_at", table_name="marking_print_batches"
    )
    op.drop_index(
        "ix_marking_print_batches_packaging_task_line_id",
        table_name="marking_print_batches",
    )
    op.drop_index(
        "ix_marking_print_batches_product_id", table_name="marking_print_batches"
    )
    op.drop_index(
        "ix_marking_print_batches_seller_id", table_name="marking_print_batches"
    )
    op.drop_index(
        "ix_marking_print_batches_tenant_id", table_name="marking_print_batches"
    )
    op.drop_table("marking_print_batches")
