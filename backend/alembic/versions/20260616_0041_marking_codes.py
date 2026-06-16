"""honest sign marking codes + product flag + packaging line qty_marking_printed

Revision ID: 20260616_0041
Revises: 20260615_0040
Create Date: 2026-06-16

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260616_0041"
down_revision = "20260615_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column(
            "requires_honest_sign",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "packaging_task_lines",
        sa.Column(
            "qty_marking_printed",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_table(
        "marking_code_imports",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("seller_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("accepted_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("skip_reasons_json", sa.Text(), nullable=True),
        sa.Column("uploaded_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_marking_code_imports_tenant_id",
        "marking_code_imports",
        ["tenant_id"],
    )
    op.create_index(
        "ix_marking_code_imports_seller_id",
        "marking_code_imports",
        ["seller_id"],
    )
    op.create_table(
        "marking_codes",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("seller_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("product_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("import_batch_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("packaging_task_line_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("cis_code", sa.String(length=512), nullable=False),
        sa.Column("gtin", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("printed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("printed_by_user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["import_batch_id"], ["marking_code_imports.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["packaging_task_line_id"], ["packaging_task_lines.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["printed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "cis_code", name="uq_marking_codes_tenant_cis"),
    )
    op.create_index("ix_marking_codes_tenant_id", "marking_codes", ["tenant_id"])
    op.create_index("ix_marking_codes_seller_id", "marking_codes", ["seller_id"])
    op.create_index("ix_marking_codes_product_id", "marking_codes", ["product_id"])
    op.create_index(
        "ix_marking_codes_import_batch_id",
        "marking_codes",
        ["import_batch_id"],
    )
    op.create_index(
        "ix_marking_codes_packaging_task_line_id",
        "marking_codes",
        ["packaging_task_line_id"],
    )
    op.create_index(
        "ix_marking_codes_tenant_seller_status",
        "marking_codes",
        ["tenant_id", "seller_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_marking_codes_tenant_seller_status", table_name="marking_codes")
    op.drop_table("marking_codes")
    op.drop_table("marking_code_imports")
    op.drop_column("packaging_task_lines", "qty_marking_printed")
    op.drop_column("products", "requires_honest_sign")
