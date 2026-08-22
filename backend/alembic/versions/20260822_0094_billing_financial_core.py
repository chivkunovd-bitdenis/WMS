"""Billing financial core: profiles, tariff versions and immutable ledger."""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision = "20260822_0094"
down_revision: str | Sequence[str] | None = "20260821_0093"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = sa.Uuid(as_uuid=True)
    op.create_table(
        "billing_profiles",
        sa.Column("id", uuid, nullable=False), sa.Column("tenant_id", uuid, nullable=False),
        sa.Column("seller_id", uuid, nullable=True), sa.Column("legal_name", sa.String(255), nullable=False),
        sa.Column("inn", sa.String(12), nullable=False), sa.Column("kpp", sa.String(9), nullable=True),
        sa.Column("bank_name", sa.String(255), nullable=True), sa.Column("bik", sa.String(9), nullable=True),
        sa.Column("settlement_account", sa.String(20), nullable=True), sa.Column("correspondent_account", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("tenant_id", "seller_id", name="uq_billing_profiles_tenant_seller"),
    )
    op.create_index("ix_billing_profiles_tenant_id", "billing_profiles", ["tenant_id"])
    op.create_index("ix_billing_profiles_seller_id", "billing_profiles", ["seller_id"])
    op.create_index(
        "uq_billing_profiles_tenant_ff",
        "billing_profiles",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("seller_id IS NULL"),
        sqlite_where=sa.text("seller_id IS NULL"),
    )

    op.create_table(
        "billing_tariff_versions",
        sa.Column("id", uuid, nullable=False), sa.Column("tenant_id", uuid, nullable=False), sa.Column("seller_id", uuid, nullable=True),
        sa.Column("service_code", sa.String(64), nullable=False), sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False), sa.Column("valid_from", sa.Date(), nullable=False), sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("unit IN ('document', 'item', 'liter_day')", name="ck_billing_tariff_unit"), sa.CheckConstraint("amount >= 0", name="ck_billing_tariff_amount_nonnegative"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "seller_id", "service_code", "unit", "valid_from", name="uq_billing_tariff_version"),
    )
    op.create_index("ix_billing_tariff_versions_tenant_id", "billing_tariff_versions", ["tenant_id"])
    op.create_index("ix_billing_tariff_versions_seller_id", "billing_tariff_versions", ["seller_id"])
    op.create_index("ix_billing_tariffs_tenant_service", "billing_tariff_versions", ["tenant_id", "service_code", "valid_from"])

    op.create_table(
        "billing_ledger_entries",
        sa.Column("id", uuid, nullable=False), sa.Column("tenant_id", uuid, nullable=False), sa.Column("seller_id", uuid, nullable=True),
        sa.Column("tariff_version_id", uuid, nullable=True), sa.Column("reversal_of_id", uuid, nullable=True), sa.Column("performer_id", uuid, nullable=True),
        sa.Column("entry_type", sa.String(16), nullable=False), sa.Column("service_code", sa.String(64), nullable=False), sa.Column("source", sa.String(64), nullable=False),
        sa.Column("source_type", sa.String(64), nullable=False), sa.Column("source_id", uuid, nullable=False), sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 4), nullable=False), sa.Column("rate", sa.Numeric(14, 2), nullable=True), sa.Column("amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("entry_type IN ('charge', 'reversal')", name="ck_billing_ledger_entry_type"), sa.CheckConstraint("unit IN ('document', 'item', 'liter_day')", name="ck_billing_ledger_unit"), sa.CheckConstraint("service_code <> ''", name="ck_billing_ledger_service_code"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="SET NULL"), sa.ForeignKeyConstraint(["tariff_version_id"], ["billing_tariff_versions.id"], ondelete="SET NULL"), sa.ForeignKeyConstraint(["reversal_of_id"], ["billing_ledger_entries.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["performer_id"], ["users.id"], ondelete="SET NULL"), sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("tenant_id", "source_type", "source_id", name="uq_billing_ledger_source_event"),
    )
    for name, column in (("tenant_id", "tenant_id"), ("seller_id", "seller_id"), ("reversal_of_id", "reversal_of_id"), ("performer_id", "performer_id")):
        op.create_index(f"ix_billing_ledger_entries_{name}", "billing_ledger_entries", [column])
    op.create_index("ix_billing_ledger_tenant_occurred", "billing_ledger_entries", ["tenant_id", "occurred_at"])


def downgrade() -> None:
    op.drop_table("billing_ledger_entries")
    op.drop_table("billing_tariff_versions")
    op.drop_table("billing_profiles")
