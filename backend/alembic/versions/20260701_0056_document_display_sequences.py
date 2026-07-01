"""document display sequences and backfill display_number

Revision ID: 20260701_0056
Revises: 20260626_0055
Create Date: 2026-07-01

"""

from __future__ import annotations

import uuid
from collections import defaultdict

import sqlalchemy as sa
from alembic import op

revision = "20260701_0056"
down_revision = "20260630_0055"
branch_labels = None
depends_on = None

DISPLAY_PREFIX = "№"

DOC_SPECS = (
    ("inbound", "inbound_intake_requests"),
    ("unload", "marketplace_unload_requests"),
    ("packaging", "packaging_tasks"),
)


def _display_number(counter: int) -> str:
    return f"{DISPLAY_PREFIX}{counter:06d}"


def _backfill_table(
    bind: sa.engine.Connection,
    table_name: str,
    doc_type: str,
) -> None:
    table = sa.table(
        table_name,
        sa.column("id", sa.Uuid()),
        sa.column("tenant_id", sa.Uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("display_number", sa.String()),
    )
    rows = list(
        bind.execute(
            sa.select(
                table.c.id,
                table.c.tenant_id,
                table.c.created_at,
            ).order_by(table.c.tenant_id, table.c.created_at, table.c.id)
        )
    )
    counters: dict[uuid.UUID, int] = defaultdict(int)
    for row in rows:
        tenant_id = row.tenant_id
        counters[tenant_id] += 1
        bind.execute(
            sa.update(table)
            .where(table.c.id == row.id)
            .values(display_number=_display_number(counters[tenant_id]))
        )

    display_sequence = sa.table(
        "document_display_sequences",
        sa.column("id", sa.Uuid()),
        sa.column("tenant_id", sa.Uuid()),
        sa.column("doc_type", sa.String()),
        sa.column("counter", sa.Integer()),
    )
    for tenant_id, counter in counters.items():
        bind.execute(
            display_sequence.insert().values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                doc_type=doc_type,
                counter=counter,
            )
        )


def upgrade() -> None:
    op.create_table(
        "document_display_sequences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("doc_type", sa.String(length=32), nullable=False),
        sa.Column("counter", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "doc_type",
            name="uq_document_display_sequences_tenant_type",
        ),
    )
    op.create_index(
        op.f("ix_document_display_sequences_tenant_id"),
        "document_display_sequences",
        ["tenant_id"],
        unique=False,
    )
    op.add_column(
        "inbound_intake_requests",
        sa.Column("display_number", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "marketplace_unload_requests",
        sa.Column("display_number", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "packaging_tasks",
        sa.Column("display_number", sa.String(length=16), nullable=True),
    )

    bind = op.get_bind()
    for doc_type, table_name in DOC_SPECS:
        _backfill_table(bind, table_name, doc_type)


def downgrade() -> None:
    op.drop_column("packaging_tasks", "display_number")
    op.drop_column("marketplace_unload_requests", "display_number")
    op.drop_column("inbound_intake_requests", "display_number")
    op.drop_index(
        op.f("ix_document_display_sequences_tenant_id"),
        table_name="document_display_sequences",
    )
    op.drop_table("document_display_sequences")
