"""add reliable operation facts

Revision ID: 20260826_0110
Revises: 20260825_0109
"""

import sqlalchemy as sa

from alembic import op

revision = "20260826_0110"
down_revision = "20260825_0109"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = sa.Uuid(as_uuid=True)
    op.create_table(
        "operation_fact_cutover",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("id = 1", name="ck_operation_fact_cutover_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "operation_facts",
        sa.Column("id", uuid, nullable=False),
        sa.Column("tenant_id", uuid, nullable=False),
        sa.Column("operation_code", sa.String(64), nullable=False),
        sa.Column("billable_service_code", sa.String(64), nullable=True),
        sa.Column("source_kind", sa.String(64), nullable=False),
        sa.Column("source_event_id", uuid, nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("seller_id", uuid, nullable=True),
        sa.Column("seller_name_snapshot", sa.String(255), nullable=True),
        sa.Column("warehouse_id", uuid, nullable=True),
        sa.Column("marketplace", sa.String(32), nullable=True),
        sa.Column("document_type", sa.String(64), nullable=False),
        sa.Column("document_id", uuid, nullable=False),
        sa.Column("document_number_snapshot", sa.String(64), nullable=True),
        sa.Column("actor_user_id", uuid, nullable=True),
        sa.Column("actor_name_snapshot", sa.String(255), nullable=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("item_quantity", sa.Integer(), nullable=False),
        sa.Column("reversal_of_id", uuid, nullable=True),
        sa.Column("integrity_status", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("operation_code <> ''", name="ck_operation_facts_operation_code"),
        sa.CheckConstraint("source_kind <> ''", name="ck_operation_facts_source_kind"),
        sa.CheckConstraint(
            "item_quantity >= 0", name="ck_operation_facts_item_quantity_nonnegative"
        ),
        sa.CheckConstraint("source IN ('user', 'system')", name="ck_operation_facts_source"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reversal_of_id"], ["operation_facts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_operation_facts_tenant_idempotency",
        "operation_facts",
        ["tenant_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        sqlite_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_index(
        "uq_operation_facts_source_operation",
        "operation_facts",
        ["tenant_id", "source_kind", "source_event_id", "operation_code"],
        unique=True,
    )
    op.create_index(
        "ix_operation_facts_seller_occurred",
        "operation_facts",
        ["tenant_id", "seller_id", "occurred_at", "id"],
    )
    op.create_index(
        "ix_operation_facts_actor_occurred",
        "operation_facts",
        ["tenant_id", "actor_user_id", "occurred_at", "id"],
    )
    op.create_index(
        "ix_operation_facts_operation_occurred",
        "operation_facts",
        ["tenant_id", "operation_code", "occurred_at", "id"],
    )
    op.create_table(
        "operation_fact_lines",
        sa.Column("id", uuid, nullable=False),
        sa.Column("operation_fact_id", uuid, nullable=False),
        sa.Column("product_id", uuid, nullable=True),
        sa.Column("sku_snapshot", sa.String(255), nullable=True),
        sa.Column("product_name_snapshot", sa.String(255), nullable=True),
        sa.Column("item_quantity", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "item_quantity >= 0", name="ck_operation_fact_lines_item_quantity_nonnegative"
        ),
        sa.ForeignKeyConstraint(["operation_fact_id"], ["operation_facts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_operation_fact_lines_fact", "operation_fact_lines", ["operation_fact_id"])
    for table, column, name in (
        ("inbound_intake_requests", "completed_by_user_id", "fk_inbound_intake_completed_by_user"),
        (
            "marketplace_unload_requests",
            "completed_by_user_id",
            "fk_marketplace_unload_completed_by_user",
        ),
        (
            "marketplace_unload_requests",
            "cancelled_by_user_id",
            "fk_marketplace_unload_cancelled_by_user",
        ),
        ("fbs_order_product_picks", "picked_by_user_id", "fk_fbs_product_pick_picked_by_user"),
        ("fbs_order_product_picks", "undone_by_user_id", "fk_fbs_product_pick_undone_by_user"),
    ):
        op.add_column(table, sa.Column(column, uuid, nullable=True))
        op.create_foreign_key(name, table, "users", [column], ["id"], ondelete="SET NULL")
    op.execute("INSERT INTO operation_fact_cutover (id, occurred_at) VALUES (1, CURRENT_TIMESTAMP)")


def downgrade() -> None:
    op.drop_table("operation_fact_lines")
    op.drop_table("operation_facts")
    op.drop_table("operation_fact_cutover")
    for table, column, name in (
        ("fbs_order_product_picks", "undone_by_user_id", "fk_fbs_product_pick_undone_by_user"),
        ("fbs_order_product_picks", "picked_by_user_id", "fk_fbs_product_pick_picked_by_user"),
        (
            "marketplace_unload_requests",
            "cancelled_by_user_id",
            "fk_marketplace_unload_cancelled_by_user",
        ),
        (
            "marketplace_unload_requests",
            "completed_by_user_id",
            "fk_marketplace_unload_completed_by_user",
        ),
        ("inbound_intake_requests", "completed_by_user_id", "fk_inbound_intake_completed_by_user"),
    ):
        op.drop_constraint(name, table, type_="foreignkey")
        op.drop_column(table, column)
