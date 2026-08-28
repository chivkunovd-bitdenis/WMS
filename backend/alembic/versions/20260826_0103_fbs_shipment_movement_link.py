"""Link every FBS shipment ledger row to its physical write-off movement.

Revision ID: 20260826_0103
Revises: 20260826_0102
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260826_0103"
down_revision: str | Sequence[str] | None = "20260826_0102"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "fbs_shipment_reversal_ledger",
        sa.Column("shipment_movement_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        "fk_fbs_shipment_reversal_movement",
        "fbs_shipment_reversal_ledger",
        "inventory_movements",
        ["shipment_movement_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint(
        "uq_fbs_shipment_reversal_movement",
        "fbs_shipment_reversal_ledger",
        ["shipment_movement_id"],
    )

    # Legacy code created the ledger and movement consecutively in one transaction,
    # so PostgreSQL gave them the same transaction timestamp.  Rank both sides to
    # preserve one-to-one mapping when several identical SKUs were shipped together.
    op.execute(
        """
        WITH ranked_ledgers AS (
            SELECT id, tenant_id, product_id, storage_location_id, created_at,
                   row_number() OVER (
                       PARTITION BY tenant_id, product_id, storage_location_id, created_at
                       ORDER BY id
                   ) AS row_num
            FROM fbs_shipment_reversal_ledger
        ), ranked_movements AS (
            SELECT id, tenant_id, product_id, storage_location_id, created_at,
                   row_number() OVER (
                       PARTITION BY tenant_id, product_id, storage_location_id, created_at
                       ORDER BY id
                   ) AS row_num
            FROM inventory_movements
            WHERE movement_type = 'fbs_shipment'
              AND quantity_delta < 0
              AND transfer_group_id IS NULL
        )
        UPDATE fbs_shipment_reversal_ledger AS ledger
        SET shipment_movement_id = movement.id
        FROM ranked_ledgers AS ranked_ledger
        JOIN ranked_movements AS movement
          ON movement.tenant_id = ranked_ledger.tenant_id
         AND movement.product_id = ranked_ledger.product_id
         AND movement.storage_location_id = ranked_ledger.storage_location_id
         AND movement.created_at = ranked_ledger.created_at
         AND movement.row_num = ranked_ledger.row_num
        WHERE ledger.id = ranked_ledger.id
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_fbs_shipment_reversal_movement",
        "fbs_shipment_reversal_ledger",
        type_="unique",
    )
    op.drop_constraint(
        "fk_fbs_shipment_reversal_movement",
        "fbs_shipment_reversal_ledger",
        type_="foreignkey",
    )
    op.drop_column("fbs_shipment_reversal_ledger", "shipment_movement_id")
