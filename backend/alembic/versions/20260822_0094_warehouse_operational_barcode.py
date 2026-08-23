"""Add operational warehouse flag and generated scan barcode."""
from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "20260822_0094"
down_revision: str | Sequence[str] | None = "20260821_0093"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("warehouses", sa.Column("is_operational", sa.Boolean(), nullable=True))
    op.add_column("warehouses", sa.Column("barcode", sa.String(length=64), nullable=True))
    conn = op.get_bind()
    t = sa.table(
        "warehouses",
        sa.column("id", sa.Uuid()),
        sa.column("tenant_id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("code", sa.String()),
        sa.column("is_operational", sa.Boolean()),
        sa.column("barcode", sa.String()),
    )
    rows = conn.execute(sa.select(t.c.id, t.c.tenant_id, t.c.name, t.c.code)).fetchall()
    for row in rows:
        legacy = row.code.lower().startswith("fbs-wb-") or row.name.lower().startswith("fbs wb ")
        conn.execute(
            sa.update(t)
            .where(t.c.id == row.id)
            .values(
                is_operational=not legacy,
                barcode=f"WH-{uuid.uuid4().hex[:12].upper()}",
            )
        )
    # Zero physical warehouses is a valid state.  Never promote a legacy
    # ``FBS WB *`` routing stub merely to manufacture an operational warehouse:
    # the operator must create the real physical warehouse explicitly.
    op.alter_column("warehouses", "is_operational", nullable=False, server_default=sa.true())
    op.alter_column("warehouses", "barcode", nullable=False)
    op.create_index("ix_warehouses_barcode", "warehouses", ["barcode"], unique=True)

def downgrade() -> None:
    op.drop_index("ix_warehouses_barcode", table_name="warehouses")
    op.drop_column("warehouses", "barcode")
    op.drop_column("warehouses", "is_operational")
