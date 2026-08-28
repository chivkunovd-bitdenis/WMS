"""add immutable additive invoice v2 snapshots

Revision ID: 20260827_0114
Revises: 20260827_0113
"""

import sqlalchemy as sa
from alembic import op

revision = "20260827_0114"
down_revision = "20260827_0113"
branch_labels = None
depends_on = None


def _has_unique_constraint(table: str, name: str) -> bool:
    """Ограничение уже стоит в базе?

    Стейдж и прод получали ревизии из двух разошедшихся линий, и это ограничение
    там уже создано другой миграцией. Повторное создание валит накатку целиком —
    приложение не поднимается вовсе. Проверка дешёвая, а без неё выкатка встаёт
    на живой базе и чинится только руками.
    """
    inspector = sa.inspect(op.get_bind())
    existing = {item["name"] for item in inspector.get_unique_constraints(table)}
    existing |= {item["name"] for item in inspector.get_indexes(table)}
    return name in existing


def upgrade() -> None:
    uuid = sa.Uuid(as_uuid=True)
    if not _has_unique_constraint("operation_facts", "uq_operation_facts_tenant_id_id"):
        op.create_unique_constraint(
            "uq_operation_facts_tenant_id_id", "operation_facts", ["tenant_id", "id"]
        )
    op.create_table(
        "billing_invoices_v2",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("tenant_id", uuid, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seller_id", uuid, sa.ForeignKey("sellers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("number", sa.String(64), nullable=False),
        sa.Column("creation_mode", sa.String(32), nullable=False),
        sa.Column("period_start", sa.Date()), sa.Column("period_end", sa.Date()),
        sa.Column("status", sa.String(16), nullable=False, server_default="issued"),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("issued_by_user_id", uuid, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("ff_profile_snapshot", sa.JSON(), nullable=False), sa.Column("seller_profile_snapshot", sa.JSON(), nullable=False),
        sa.Column("total_amount_kopecks", sa.Integer(), nullable=False),
        sa.UniqueConstraint("tenant_id", "id", name="uq_billing_invoices_v2_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "number", name="uq_billing_invoices_v2_tenant_number"),
        sa.CheckConstraint("creation_mode IN ('selected_operations', 'manual')", name="ck_billing_invoice_v2_mode"),
        sa.CheckConstraint("status IN ('issued', 'cancelled')", name="ck_billing_invoice_v2_status"),
        sa.CheckConstraint("(period_start IS NULL AND period_end IS NULL) OR period_end >= period_start", name="ck_billing_invoice_v2_period"),
    )
    op.create_index("ix_billing_invoices_v2_tenant_issued", "billing_invoices_v2", ["tenant_id", "issued_at", "id"])
    op.create_table(
        "billing_invoice_v2_lines",
        sa.Column("id", uuid, primary_key=True), sa.Column("tenant_id", uuid, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invoice_id", uuid, nullable=False), sa.Column("description_snapshot", sa.String(255), nullable=False),
        sa.Column("unit_price_kopecks", sa.Integer()), sa.Column("total_amount_kopecks", sa.Integer(), nullable=False), sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.UniqueConstraint("tenant_id", "id", name="uq_billing_invoice_v2_lines_tenant_id_id"),
        sa.ForeignKeyConstraint(["tenant_id", "invoice_id"], ["billing_invoices_v2.tenant_id", "billing_invoices_v2.id"], name="fk_billing_invoice_v2_line_tenant_invoice", ondelete="RESTRICT"),
    )
    op.create_index("ix_billing_invoice_v2_lines_tenant_invoice", "billing_invoice_v2_lines", ["tenant_id", "invoice_id"])
    op.create_table(
        "billing_invoice_v2_sources",
        sa.Column("id", uuid, primary_key=True), sa.Column("tenant_id", uuid, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False), sa.Column("invoice_line_id", uuid, nullable=False),
        sa.Column("operation_fact_id", uuid), sa.Column("billing_ledger_entry_id", uuid), sa.Column("storage_calculation_token", sa.String(4096)), sa.Column("signed_amount_kopecks_snapshot", sa.Integer(), nullable=False),
        sa.UniqueConstraint("tenant_id", "id", name="uq_billing_invoice_v2_sources_tenant_id_id"),
        sa.ForeignKeyConstraint(["tenant_id", "invoice_line_id"], ["billing_invoice_v2_lines.tenant_id", "billing_invoice_v2_lines.id"], name="fk_billing_invoice_v2_source_tenant_line", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "operation_fact_id"], ["operation_facts.tenant_id", "operation_facts.id"], name="fk_billing_invoice_v2_source_tenant_fact", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id", "billing_ledger_entry_id"], ["billing_ledger_entries.tenant_id", "billing_ledger_entries.id"], name="fk_billing_invoice_v2_source_tenant_ledger", ondelete="RESTRICT"),
        sa.CheckConstraint("(CASE WHEN operation_fact_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN billing_ledger_entry_id IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN storage_calculation_token IS NOT NULL THEN 1 ELSE 0 END) = 1", name="ck_billing_invoice_v2_source_one_target"),
    )
    for name, columns in (("ix_billing_invoice_v2_sources_tenant_fact", ["tenant_id", "operation_fact_id"]), ("ix_billing_invoice_v2_sources_tenant_ledger", ["tenant_id", "billing_ledger_entry_id"]), ("ix_billing_invoice_v2_sources_tenant_line", ["tenant_id", "invoice_line_id"])):
        op.create_index(name, "billing_invoice_v2_sources", columns)
    op.create_table(
        "billing_invoice_v2_idempotency",
        sa.Column("id", uuid, primary_key=True), sa.Column("tenant_id", uuid, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False), sa.Column("user_id", uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("request_key", sa.String(255), nullable=False), sa.Column("request_hash", sa.String(64), nullable=False), sa.Column("invoice_id", uuid, nullable=False),
        sa.UniqueConstraint("tenant_id", "user_id", "request_key", name="uq_billing_invoice_v2_idempotency_request"),
    )


def downgrade() -> None:
    op.drop_table("billing_invoice_v2_idempotency")
    op.drop_table("billing_invoice_v2_sources")
    op.drop_table("billing_invoice_v2_lines")
    op.drop_table("billing_invoices_v2")
    if _has_unique_constraint("operation_facts", "uq_operation_facts_tenant_id_id"):
        op.drop_constraint("uq_operation_facts_tenant_id_id", "operation_facts", type_="unique")
