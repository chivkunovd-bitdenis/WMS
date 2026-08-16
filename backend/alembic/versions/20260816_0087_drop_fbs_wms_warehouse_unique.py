"""Drop one-WMS-warehouse-per-seller unique constraint on FBS bindings.

One physical WMS warehouse now feeds every WB warehouse address for a
seller (pool 1, item 5 of docs/agent-orders/HANDOFF-POLISH.md) — the
former uniqueness on (seller_id, wms_warehouse_id) blocked live-order
binding on staging (PUT .../warehouse-bindings/1155120 -> 409
wms_warehouse_already_bound).

Revision ID: 20260816_0087
Revises: 20260815_0086
Create Date: 2026-08-16
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260816_0087"
down_revision: str | Sequence[str] | None = "20260815_0086"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_fbs_warehouse_bindings_seller_wms_warehouse",
        "fbs_warehouse_bindings",
        type_="unique",
    )


def downgrade() -> None:
    op.create_unique_constraint(
        "uq_fbs_warehouse_bindings_seller_wms_warehouse",
        "fbs_warehouse_bindings",
        ["seller_id", "wms_warehouse_id"],
    )
