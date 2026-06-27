"""document sequences and document_number on operational docs

Revision ID: 20260626_0042
Revises: 20260616_0041
Create Date: 2026-06-26

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260626_0042"
down_revision = "20260616_0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_sequences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("doc_type", sa.String(length=32), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("counter", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "doc_type",
            "date",
            name="uq_document_sequences_tenant_type_date",
        ),
    )
    op.create_index(
        op.f("ix_document_sequences_tenant_id"),
        "document_sequences",
        ["tenant_id"],
        unique=False,
    )
    op.add_column(
        "packaging_tasks",
        sa.Column("document_number", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "inbound_intake_requests",
        sa.Column("document_number", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "marketplace_unload_requests",
        sa.Column("document_number", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("marketplace_unload_requests", "document_number")
    op.drop_column("inbound_intake_requests", "document_number")
    op.drop_column("packaging_tasks", "document_number")
    op.drop_index(op.f("ix_document_sequences_tenant_id"), table_name="document_sequences")
    op.drop_table("document_sequences")
