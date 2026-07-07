"""marking_code_import_files — durable storage metadata for source PDF uploads."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260707_0058"
down_revision = "20260705_0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "marking_code_import_files",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("import_batch_id", sa.Uuid(), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256_hex", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["import_batch_id"], ["marking_code_imports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_marking_code_import_files_tenant_id",
        "marking_code_import_files",
        ["tenant_id"],
    )
    op.create_index(
        "ix_marking_code_import_files_import_batch_id",
        "marking_code_import_files",
        ["import_batch_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_marking_code_import_files_import_batch_id", table_name="marking_code_import_files")
    op.drop_index("ix_marking_code_import_files_tenant_id", table_name="marking_code_import_files")
    op.drop_table("marking_code_import_files")
