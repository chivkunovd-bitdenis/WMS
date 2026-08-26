"""add tariff matrix v2 and immutable ledger lines

Revision ID: 20260826_0112
Revises: 20260826_0111
"""

import sqlalchemy as sa
from alembic import op

revision = "20260826_0112"
down_revision = "20260826_0111"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = sa.Uuid(as_uuid=True)
    op.create_table(
        "billing_tariff_matrix_configs",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("tenant_id", uuid, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", name="uq_billing_tariff_matrix_config_tenant"),
    )
    op.execute(
        "INSERT INTO billing_tariff_matrix_configs (id, tenant_id, revision) "
        "SELECT gen_random_uuid(), id, 0 FROM tenants"
    )
    op.create_table(
        "billing_tariff_service_states",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("config_id", uuid, sa.ForeignKey("billing_tariff_matrix_configs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", uuid, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("service_code", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("tenant_id", "service_code", name="uq_billing_tariff_service_state"),
        sa.CheckConstraint("service_code IN ('inbound', 'marketplace_outbound', 'packing', 'return')", name="ck_billing_tariff_service_state_code"),
    )
    op.execute(
        "INSERT INTO billing_tariff_service_states (id, config_id, tenant_id, service_code, enabled) "
        "SELECT gen_random_uuid(), config.id, config.tenant_id, service.service_code, "
        "CASE WHEN service.service_code IN ('inbound', 'marketplace_outbound') THEN true ELSE false END "
        "FROM billing_tariff_matrix_configs config "
        "CROSS JOIN (VALUES ('inbound'), ('marketplace_outbound'), ('packing'), ('return')) AS service(service_code)"
    )
    op.create_table(
        "billing_tariff_versions_v2",
        sa.Column("id", uuid, primary_key=True), sa.Column("tenant_id", uuid, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seller_id", uuid, sa.ForeignKey("sellers.id", ondelete="RESTRICT")), sa.Column("product_id", uuid, sa.ForeignKey("products.id", ondelete="RESTRICT")),
        sa.Column("employee_user_id", uuid, sa.ForeignKey("users.id", ondelete="RESTRICT")), sa.Column("service_code", sa.String(64), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False), sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("rate", sa.Integer(), nullable=False), sa.Column("valid_from_at", sa.DateTime(timezone=True), nullable=False), sa.Column("valid_to_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("unit IN ('document', 'item')", name="ck_billing_tariff_v2_unit"), sa.CheckConstraint("rate >= 0", name="ck_billing_tariff_v2_rate_nonnegative"),
        sa.CheckConstraint("valid_to_at IS NULL OR valid_to_at > valid_from_at", name="ck_billing_tariff_v2_interval"),
    )
    op.add_column("billing_ledger_entries", sa.Column("tariff_version_v2_id", uuid, nullable=True))
    op.create_foreign_key("fk_billing_ledger_v2_tariff", "billing_ledger_entries", "billing_tariff_versions_v2", ["tariff_version_v2_id"], ["id"], ondelete="SET NULL")
    op.create_table(
        "billing_ledger_lines",
        sa.Column("id", uuid, primary_key=True), sa.Column("tenant_id", uuid, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ledger_entry_id", uuid, sa.ForeignKey("billing_ledger_entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("operation_fact_line_id", uuid, sa.ForeignKey("operation_fact_lines.id", ondelete="SET NULL")), sa.Column("product_id", uuid, sa.ForeignKey("products.id", ondelete="SET NULL")),
        sa.Column("product_snapshot", sa.JSON(), nullable=False), sa.Column("physical_quantity", sa.Numeric(14, 4), nullable=False), sa.Column("billing_quantity", sa.Numeric(14, 4), nullable=False),
        sa.Column("billing_unit", sa.String(16), nullable=False), sa.Column("tariff_version_v2_id", uuid, sa.ForeignKey("billing_tariff_versions_v2.id", ondelete="SET NULL")),
        sa.Column("tariff_snapshot", sa.JSON(), nullable=False), sa.Column("rate", sa.Integer()), sa.Column("amount", sa.Integer()), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("billing_unit IN ('document', 'item')", name="ck_billing_ledger_line_unit"), sa.CheckConstraint("amount IS NULL OR rate IS NOT NULL", name="ck_billing_ledger_line_amount_rate"),
    )
    op.add_column("packaging_tasks", sa.Column("billing_rate_configured", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute("UPDATE packaging_tasks SET billing_rate_configured = (billing_rate_kopecks IS NOT NULL AND billing_rate_kopecks <> 0)")


def downgrade() -> None:
    raise RuntimeError("billing tariff history is append-only; downgrade is not supported")
