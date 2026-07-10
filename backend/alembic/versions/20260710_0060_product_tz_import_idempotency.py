"""Add durable product TZ import idempotency records."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260710_0060"
down_revision = "20260709_0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_tz_imports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("seller_id", sa.Uuid(), nullable=False),
        sa.Column("warehouse_id", sa.Uuid(), nullable=True),
        sa.Column("warehouse_scope", sa.String(length=36), nullable=False),
        sa.Column("import_type", sa.String(length=64), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("declared_total", sa.Integer(), nullable=False),
        sa.Column("movement_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["warehouse_id"], ["warehouses.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "seller_id",
            "warehouse_scope",
            "import_type",
            "file_sha256",
            name="uq_product_tz_import_scope_hash",
        ),
    )
    op.create_index(
        "ix_product_tz_imports_tenant_id",
        "product_tz_imports",
        ["tenant_id"],
    )
    op.create_index(
        "ix_product_tz_imports_seller_id",
        "product_tz_imports",
        ["seller_id"],
    )
    op.create_index(
        "ix_product_tz_imports_warehouse_id",
        "product_tz_imports",
        ["warehouse_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_product_tz_imports_warehouse_id", table_name="product_tz_imports"
    )
    op.drop_index(
        "ix_product_tz_imports_seller_id", table_name="product_tz_imports"
    )
    op.drop_index(
        "ix_product_tz_imports_tenant_id", table_name="product_tz_imports"
    )
    op.drop_table("product_tz_imports")
