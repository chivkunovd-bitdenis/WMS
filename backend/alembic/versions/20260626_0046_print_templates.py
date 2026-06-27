"""print_templates

Revision ID: 20260626_0046
Revises: 20260626_0045
Create Date: 2026-06-26

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260626_0046"
down_revision = "20260626_0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "print_templates",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seller_id", sa.Uuid(as_uuid=True), sa.ForeignKey("sellers.id", ondelete="CASCADE"), nullable=True),
        sa.Column("product_id", sa.Uuid(as_uuid=True), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("layout_json", sa.Text(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_print_templates_tenant_id", "print_templates", ["tenant_id"])
    op.create_index("ix_print_templates_seller_id", "print_templates", ["seller_id"])
    op.create_index("ix_print_templates_product_id", "print_templates", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_print_templates_product_id", table_name="print_templates")
    op.drop_index("ix_print_templates_seller_id", table_name="print_templates")
    op.drop_index("ix_print_templates_tenant_id", table_name="print_templates")
    op.drop_table("print_templates")
