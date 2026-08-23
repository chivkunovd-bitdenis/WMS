"""Add immutable billing invoices and run issues."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "20260822_09b"
down_revision: str | Sequence[str] | None = "20260822_09a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    u = sa.Uuid(as_uuid=True)
    op.create_table(
        "billing_invoices",
        sa.Column("id", u, primary_key=True),
        sa.Column("tenant_id", u, nullable=False),
        sa.Column("seller_id", u, nullable=False),
        sa.Column("number", sa.String(64), nullable=False),
        sa.Column("period", sa.Date, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "issued_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("ff_profile_snapshot", sa.JSON, nullable=False),
        sa.Column("seller_profile_snapshot", sa.JSON, nullable=False),
        sa.Column("lines", sa.JSON, nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", "seller_id", "period", name="uq_billing_invoice_period"),
        sa.UniqueConstraint("tenant_id", "number", name="uq_billing_invoice_tenant_number"),
    )
    op.create_index("ix_billing_invoices_tenant_id", "billing_invoices", ["tenant_id"])
    op.create_index("ix_billing_invoices_seller_id", "billing_invoices", ["seller_id"])
    op.create_table(
        "billing_run_issues",
        sa.Column("id", u, primary_key=True),
        sa.Column("tenant_id", u, nullable=False),
        sa.Column("seller_id", u, nullable=False),
        sa.Column("period", sa.Date, nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("message", sa.String(255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "tenant_id", "seller_id", "period", "reason", name="uq_billing_run_issue"
        ),
    )
    op.create_index("ix_billing_run_issues_tenant_id", "billing_run_issues", ["tenant_id"])
    op.create_index("ix_billing_run_issues_seller_id", "billing_run_issues", ["seller_id"])


def downgrade() -> None:
    op.drop_table("billing_run_issues")
    op.drop_table("billing_invoices")
