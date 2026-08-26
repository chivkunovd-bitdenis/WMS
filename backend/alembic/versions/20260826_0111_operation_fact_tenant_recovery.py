"""enforce operation fact tenant boundaries and durable unload recovery markers

Revision ID: 20260826_0111
Revises: 20260826_0110
"""

import sqlalchemy as sa

from alembic import op

revision = "20260826_0111"
down_revision = "20260826_0110"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = sa.Uuid(as_uuid=True)
    op.add_column("operation_fact_lines", sa.Column("tenant_id", uuid, nullable=True))
    op.execute(
        """
        UPDATE operation_fact_lines AS line
        SET tenant_id = fact.tenant_id
        FROM operation_facts AS fact
        WHERE fact.id = line.operation_fact_id
        """
    )
    op.create_check_constraint(
        "ck_operation_fact_lines_tenant_required",
        "operation_fact_lines",
        "tenant_id IS NOT NULL",
    )
    op.create_foreign_key(
        "fk_operation_fact_lines_tenant",
        "operation_fact_lines",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.add_column(
        "marketplace_unload_requests", sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "marketplace_unload_requests",
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )

    for table in ("sellers", "warehouses", "users", "products", "operation_facts"):
        op.create_unique_constraint(f"uq_{table}_tenant_id_id", table, ["tenant_id", "id"])

    op.create_foreign_key(
        "fk_operation_facts_tenant_seller",
        "operation_facts",
        "sellers",
        ["tenant_id", "seller_id"],
        ["tenant_id", "id"],
    )
    op.create_foreign_key(
        "fk_operation_facts_tenant_warehouse",
        "operation_facts",
        "warehouses",
        ["tenant_id", "warehouse_id"],
        ["tenant_id", "id"],
    )
    op.create_foreign_key(
        "fk_operation_facts_tenant_actor",
        "operation_facts",
        "users",
        ["tenant_id", "actor_user_id"],
        ["tenant_id", "id"],
    )
    op.create_foreign_key(
        "fk_operation_facts_tenant_reversal",
        "operation_facts",
        "operation_facts",
        ["tenant_id", "reversal_of_id"],
        ["tenant_id", "id"],
    )
    op.create_foreign_key(
        "fk_operation_fact_lines_tenant_fact",
        "operation_fact_lines",
        "operation_facts",
        ["tenant_id", "operation_fact_id"],
        ["tenant_id", "id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_operation_fact_lines_tenant_product",
        "operation_fact_lines",
        "products",
        ["tenant_id", "product_id"],
        ["tenant_id", "id"],
    )


def downgrade() -> None:
    raise RuntimeError("operation fact history is append-only; downgrade is not supported")
