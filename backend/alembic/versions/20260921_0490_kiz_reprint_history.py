"""WMS-489: persist scanned KIZ reprints outside marking pools.

Revision ID: 20260921_0490
Revises: 20260921_0489
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260921_0490"
down_revision = "20260921_0489"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kiz_reprints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("seller_id", sa.Uuid(), nullable=False),
        sa.Column("kiz", sa.String(length=512), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("print_claim_key", sa.String(length=128), nullable=True),
        sa.Column("print_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["seller_id"], ["sellers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "seller_id",
            "idempotency_key",
            name="uq_kiz_reprints_tenant_seller_idempotency",
        ),
    )
    op.create_index("ix_kiz_reprints_tenant_id", "kiz_reprints", ["tenant_id"])
    op.create_index("ix_kiz_reprints_seller_id", "kiz_reprints", ["seller_id"])
    op.create_index("ix_kiz_reprints_created_at", "kiz_reprints", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_kiz_reprints_created_at", table_name="kiz_reprints")
    op.drop_index("ix_kiz_reprints_seller_id", table_name="kiz_reprints")
    op.drop_index("ix_kiz_reprints_tenant_id", table_name="kiz_reprints")
    op.drop_table("kiz_reprints")
