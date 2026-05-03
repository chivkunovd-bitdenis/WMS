"""storage_locations barcode

Revision ID: a06ee1327d13
Revises: 0024
Create Date: 2026-04-22 19:39:58.057827

"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a06ee1327d13'
down_revision: Union[str, Sequence[str], None] = '0024'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "storage_locations",
        sa.Column("barcode", sa.String(length=64), nullable=True),
    )
    op.create_index(
        op.f("ix_storage_locations_barcode"),
        "storage_locations",
        ["barcode"],
    )

    conn = op.get_bind()
    storage_locations = sa.table(
        "storage_locations",
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("tenant_id", sa.Uuid(as_uuid=True)),
        sa.column("barcode", sa.String(length=64)),
    )
    rows = conn.execute(sa.select(storage_locations.c.id)).fetchall()
    for (loc_id,) in rows:
        conn.execute(
            sa.update(storage_locations)
            .where(storage_locations.c.id == loc_id)
            .values(barcode=f"LOC-{uuid.uuid4().hex[:12].upper()}")
        )

    op.alter_column("storage_locations", "barcode", nullable=False)
    op.create_unique_constraint(
        "uq_storage_locations_tenant_barcode",
        "storage_locations",
        ["tenant_id", "barcode"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_storage_locations_tenant_barcode",
        "storage_locations",
        type_="unique",
    )
    op.drop_index(op.f("ix_storage_locations_barcode"), table_name="storage_locations")
    op.drop_column("storage_locations", "barcode")
